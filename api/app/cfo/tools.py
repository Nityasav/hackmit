"""Read-only, scoped tools with enforced budgets and observed review provenance."""

from collections.abc import Callable
from hashlib import sha256

from .ports import DataSource
from .schemas import Calculation, Claim, Run, Scope, SourceSpan, TaskState


class BoundaryError(ValueError):
    pass


class BudgetExceeded(BoundaryError):
    pass


class EvidenceTools:
    def __init__(self, data: DataSource, scope: Scope, run: Run, task: TaskState,
                 actor: str, emit: Callable, allowed_sources: list[str]):
        self._data, self._scope = data, scope
        self._run, self._task = run, task
        self._actor, self._emit = actor, emit
        self._allowed = set(allowed_sources)
        self.reads: set[str] = set()
        self.calculations: dict[str, Calculation] = {}

    @property
    def remaining(self) -> int:
        """Evidence calls this actor may still make on this task.

        Exposed so an adapter can plan within its allowance instead of
        discovering the limit by hitting it. It is advisory only: `_charge`
        remains the enforcement point, and the budget is shared across a task's
        review attempts, so an adapter that spends it all leaves none for a retry.
        """
        limits = self._run.request.limits
        return max(0, min(limits.tool_calls_per_agent_task - self._task.actor_tool_calls.get(self._actor, 0),
                          limits.max_tool_calls - self._run.tool_calls))

    def _charge(self, operation: str, reference: str) -> None:
        limits = self._run.request.limits
        used = self._task.actor_tool_calls.get(self._actor, 0)
        if used >= limits.tool_calls_per_agent_task or self._run.tool_calls >= limits.max_tool_calls:
            raise BudgetExceeded("Evidence tool budget exhausted; remaining work is unresolved.")
        self._task.tool_calls += 1
        self._task.actor_tool_calls[self._actor] = used + 1
        self._run.tool_calls += 1
        self._emit(self._actor, operation + ".started", reference, self._task.spec.id, [reference])

    async def read_source(self, source_id: str) -> SourceSpan:
        if source_id not in self._allowed:
            raise BoundaryError("Source is outside the delegated scope.")
        self._charge("read_source", source_id)
        value = SourceSpan.model_validate(await self._data.read_source(self._scope, source_id))
        if value.id != source_id or value.snapshot_id != self._scope.snapshot_id:
            raise BoundaryError("Source ID or snapshot mismatch.")
        self.reads.add(source_id)
        digest = sha256(value.text.encode("utf-8")).hexdigest()
        self._emit(self._actor, "read_source.completed", f"{value.locator}; sha256={digest}", self._task.spec.id, [source_id])
        return value

    async def calculate(self, calculation_id: str) -> Calculation:
        available = {c.id: c for c in self._scope.calculations}
        if calculation_id not in available or not set(available[calculation_id].source_ids).issubset(self._allowed):
            raise BoundaryError("Calculation is outside the delegated inventory.")
        self._charge("calculate", calculation_id)
        value = Calculation.model_validate(await self._data.calculate(self._scope, calculation_id))
        if value.id != calculation_id or value.snapshot_id != self._scope.snapshot_id:
            raise BoundaryError("Calculation ID or snapshot mismatch.")
        if not set(value.source_ids).issubset(self._allowed):
            raise BoundaryError("Calculation depends on sources outside the delegated scope.")
        self.calculations[value.id] = value
        self._emit(self._actor, "calculate.completed", value.model_dump_json(), self._task.spec.id, [value.id])
        return value

    def validate_claim(self, claim: Claim) -> Calculation | None:
        if not set(claim.evidence_ids).issubset(self.reads):
            raise BoundaryError("Claim cites evidence this agent did not retrieve.")
        if claim.calculation_id is None:
            return None
        calc = self.calculations.get(claim.calculation_id)
        if calc is None:
            raise BoundaryError("Claim calculation was not performed by this agent.")
        if not set(calc.source_ids).issubset(set(claim.evidence_ids)):
            raise BoundaryError("Claim omits calculation source evidence.")
        return calc
