"""Linda implements Specialist/Auditor; Maxim implements DataSource.

Adapters must be scoped, read-only and cancellation-aware. A tool timeout cancels
the await; external operations already sent cannot necessarily be rolled back.
"""

from typing import Protocol, TYPE_CHECKING

from .schemas import Calculation, Claim, FollowUp, Narrative, Plan, Review, Run, Scope, SourceSpan, TaskSpec, WorkerResult

if TYPE_CHECKING:
    from .tools import EvidenceTools


class DataSource(Protocol):
    async def snapshot(self, workspace: str) -> Scope: ...
    async def read_source(self, scope: Scope, source_id: str) -> SourceSpan: ...
    async def calculate(self, scope: Scope, calculation_id: str) -> Calculation: ...


class Specialist(Protocol):
    async def investigate(
        self, task: TaskSpec, scope: Scope, tools: "EvidenceTools",
        dependencies: list[WorkerResult], feedback: str | None,
    ) -> WorkerResult: ...


class Auditor(Protocol):
    async def review(self, claim: Claim, scope: Scope, tools: "EvidenceTools") -> Review: ...


class CFOModel(Protocol):
    label: str
    async def plan(self, objective: str, scope: Scope) -> Plan: ...
    async def follow_up(self, task: TaskSpec, claim: Claim, review: Review) -> FollowUp: ...
    async def synthesize(self, run: Run) -> Narrative: ...
