"""Payroll & Budget specialist (role `py`) backed by OpenAI structured output.

Implements `app.cfo.ports.Specialist`. The agent ties out payroll and tests fund
allocations: it decides what evidence to retrieve, retrieves it through the
coordinator's scoped read-only gateway, reads deterministic amounts from the
accounting engine, and returns typed claims that cite both.

The division of labour is deliberate and is what makes the output reviewable:

  the model chooses *what to look at* and *what it means*
  the engine decides *how much*, and the auditor reperforms that same number

So every amount in a claim is a `calculation_id` produced by
`app/accounting/payroll.py`, never a figure the model wrote. Claims that cite
evidence the agent did not actually retrieve, name a calculation it did not run,
or state a currency amount in prose are dropped here rather than being allowed to
reach the coordinator, which would fail the whole task as a boundary violation.

Bounded by construction: one evidence step and one findings step per attempt, a
per-task model-call allowance, and whatever evidence-tool budget the coordinator
grants. Exhausting a budget degrades to a partial, honest answer; it never
invents the rest.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, ValidationError

from ..cfo.schemas import Claim, WorkerResult
from ..cfo.tools import BoundaryError, BudgetExceeded
from .model import ModelBudgetExceeded, SpecialistRefusal, StructuredSpecialistModel
from .prompts import PAYROLL_BUDGET, SPECIALIST_GUARDRAILS

SYSTEM = PAYROLL_BUDGET + "\n\n" + SPECIALIST_GUARDRAILS

# Currency symbols, money-shaped decimals, grouped thousands, or a percentage.
# Bare identifiers such as PAY-1 or EMP-01 stay legal, so findings can name records.
MONEY_IN_PROSE = re.compile(r"[$€£¥]|\d[\d,]*\.\d{2}\b|\b\d{1,3}(?:,\d{3})+\b|\d\s*%|percent\b", re.IGNORECASE)
MAX_CLAIMS = 8
MAX_EVIDENCE_REQUESTS = 8
# A task's evidence allowance is shared across its review attempts, so the first
# pass keeps a share back for the targeted retry that follows an auditor challenge.
FIRST_ATTEMPT_SHARE = 0.7
MIN_ATTEMPT_BUDGET = 3


class EvidenceSelection(BaseModel):
    """Step one: what this task needs to look at, chosen from the delegated scope."""

    model_config = ConfigDict(extra="forbid")

    focus: str
    source_ids: list[str]
    calculation_ids: list[str]


class DraftClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    event_key: str
    title: str
    conclusion: str
    disposition: str
    evidence_ids: list[str]
    calculation_id: str | None
    proposed_action: str


class DraftFindings(BaseModel):
    """Step two: conclusions drawn only from what was actually retrieved."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    claims: list[DraftClaim]
    evidence_requests: list[str]


def _identifier(value: str) -> str:
    """Coerce a model-chosen ID into the coordinator's key shape, or empty."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "-", value.strip())[:60].strip("-")
    return cleaned


class PayrollBudgetSpecialist:
    """The `py` specialist. One instance serves many tasks; state is per call."""

    role = "py"
    display_name = "Payroll & Budget"
    system_prompt = SYSTEM

    def __init__(self, model: StructuredSpecialistModel):
        self.model = model

    @classmethod
    def from_env(cls) -> "PayrollBudgetSpecialist":
        return cls(StructuredSpecialistModel.from_env())

    @property
    def label(self) -> str:
        return self.model.label

    async def investigate(self, task, scope, tools, dependencies, feedback) -> WorkerResult:
        if not scope.sources:
            return WorkerResult(summary="No payroll sources were delegated to this task.",
                                evidence_requests=["Delegate payroll, award and ledger sources before this task can proceed."])
        self.model.reset()
        catalogue = {
            "task": {"id": task.id, "objective": task.objective, "success_criteria": task.success_criteria},
            "institution": scope.institution,
            "period": scope.period,
            "accounting_profile": scope.accounting_profile,
            "sources": [{"id": s.id, "title": s.title, "locator": s.locator, "domain": s.domain} for s in scope.sources],
            "calculations": [{"id": c.id, "description": c.description, "requires_sources": c.source_ids}
                             for c in scope.calculations],
            "known_gaps": scope.gaps,
            "completed_dependencies": [{"summary": d.summary, "claims": [c.title for c in d.claims]} for d in dependencies],
            "auditor_feedback": feedback,
        }
        budget = _attempt_budget(tools, retry=feedback is not None)
        catalogue["evidence_calls_available"] = budget
        if budget <= 0:
            return WorkerResult(summary="No evidence budget remained for this payroll task.",
                                evidence_requests=["Increase the evidence tool budget; payroll evidence was never retrieved."])
        try:
            selection = await self.model.generate(self.system_prompt, self._SELECT_INSTRUCTION, catalogue, EvidenceSelection)
        except (ModelBudgetExceeded, SpecialistRefusal) as exc:
            return WorkerResult(summary=f"Evidence selection unavailable ({type(exc).__name__}); no conclusions drawn.",
                                evidence_requests=["Retry the payroll task; the specialist model did not return a usable evidence plan."])

        reads, computed, notes = await self._gather(selection, scope, tools, budget)
        if not reads:
            return WorkerResult(
                summary="No payroll evidence could be retrieved within this task's scope and budget.",
                evidence_requests=(notes or ["Grant payroll evidence access or increase the evidence budget for this task."])[:MAX_EVIDENCE_REQUESTS])

        retrieved = {
            "task": catalogue["task"],
            "institution": scope.institution,
            "period": scope.period,
            "accounting_profile": scope.accounting_profile,
            "focus": selection.focus,
            "auditor_feedback": feedback,
            "completed_dependencies": catalogue["completed_dependencies"],
            "evidence": [{"source_id": span.id, "locator": span.locator, "text": span.text} for span in reads.values()],
            "calculations": [{"id": c.id, "description": c.description, "category": c.category,
                              "amount_cents": c.amount_cents, "cash_delta_cents": c.cash_delta_cents,
                              "requires_evidence": c.source_ids} for c in computed.values()],
            "evidence_not_retrieved": notes,
        }
        try:
            findings = await self.model.generate(self.system_prompt, self._FINDINGS_INSTRUCTION, retrieved, DraftFindings)
        except (ModelBudgetExceeded, SpecialistRefusal) as exc:
            return WorkerResult(summary=f"Payroll evidence was retrieved but no reviewable conclusion was produced ({type(exc).__name__}).",
                                evidence_requests=["Retry the payroll task; the specialist model did not return usable findings."])

        claims, rejected = self._validate(findings.claims, set(reads), computed)
        requests = [r.strip()[:2000] for r in findings.evidence_requests if r.strip()]
        requests += notes + rejected
        summary = findings.summary.strip()[:2000] or "Payroll review completed."
        if not claims and not requests:
            requests = ["Payroll evidence was read but supported no reviewable conclusion; supply the records named in the summary."]
        return WorkerResult(summary=summary, claims=claims[:MAX_CLAIMS],
                            evidence_requests=_unique(requests)[:MAX_EVIDENCE_REQUESTS])

    async def _gather(self, selection: EvidenceSelection, scope, tools, budget: int):
        """Retrieve the chosen evidence, staying inside scope and budget.

        Reads come first and calculations take what is left, because a
        calculation whose sources were not retrieved cannot be cited by a claim.
        """
        offered_sources = {s.id for s in scope.sources}
        offered_calculations = {c.id: c for c in scope.calculations}
        notes: list[str] = []

        requested_calculations = _unique([c for c in selection.calculation_ids if c in offered_calculations])
        chosen = _unique([s for s in selection.source_ids if s in offered_sources])

        # Reads and calculations draw on one allowance, so plan them together. The
        # agent's own source picks come first: a document establishes the criterion
        # an amount is tested against, and an amount with no criterion proves little.
        # A calculation is then added only if its unread sources and its own call
        # both still fit, since a claim must cite every source a calculation rests on.
        order: list[str] = []
        wanted_calculations: list[str] = []
        spent = 0
        # Never reserve the last call away from reading anything at all.
        reserved = 1 if requested_calculations and budget >= 2 else 0
        for source_id in chosen:
            if spent + 1 > budget - reserved:
                break
            order.append(source_id)
            spent += 1
        # Record this before calculation prerequisites extend `order` and hide it.
        chosen_dropped = len(order) < len(chosen)
        for calculation_id in requested_calculations:
            missing = [s for s in offered_calculations[calculation_id].source_ids if s not in order]
            if spent + len(missing) + 1 > budget:
                continue
            order.extend(missing)
            wanted_calculations.append(calculation_id)
            spent += len(missing) + 1
        if chosen_dropped or len(wanted_calculations) < len(requested_calculations):
            notes.append("The evidence budget for this task did not cover everything this payroll review "
                         "selected; the remaining payroll evidence is unreviewed.")

        reads, computed = {}, {}
        budget_spent = False
        for source_id in order:
            try:
                span = await tools.read_source(source_id)
            except BudgetExceeded:
                budget_spent = True
                break
            except BoundaryError:
                notes.append(f"Source {source_id} is outside this task's delegated scope.")
                continue
            reads[source_id] = span

        for calculation_id in wanted_calculations:
            if budget_spent:
                break
            if not set(offered_calculations[calculation_id].source_ids).issubset(reads):
                notes.append(f"Calculation {calculation_id} was skipped: its source evidence was not retrieved.")
                continue
            try:
                computed[calculation_id] = await tools.calculate(calculation_id)
            except BudgetExceeded:
                budget_spent = True
                break
            except BoundaryError:
                notes.append(f"Calculation {calculation_id} is outside this task's delegated inventory.")
        if budget_spent:
            notes.append("The evidence budget for this task was exhausted; remaining payroll evidence is unreviewed.")
        return reads, computed, notes

    def _validate(self, drafts: list[DraftClaim], read_ids: set[str], computed: dict):
        """Keep only claims the coordinator and auditor will be able to verify."""
        claims: list[Claim] = []
        rejected: list[str] = []
        seen: set[str] = set()
        for draft in drafts:
            claim_id = _identifier(draft.id)
            if not claim_id or claim_id in seen:
                rejected.append("A draft payroll conclusion was withheld: missing or duplicate claim identifier.")
                continue
            evidence = _unique([e for e in draft.evidence_ids if e in read_ids])
            calculation = computed.get(draft.calculation_id) if draft.calculation_id else None
            if draft.calculation_id and calculation is None:
                rejected.append(f"A draft payroll conclusion was withheld: it cited calculation {draft.calculation_id}, which this agent did not perform.")
                continue
            if calculation is not None:
                # validate_claim requires the calculation's own sources among the cited evidence.
                evidence = _unique(evidence + [s for s in calculation.source_ids if s in read_ids])
                if not set(calculation.source_ids).issubset(evidence):
                    rejected.append(f"A draft payroll conclusion was withheld: calculation {calculation.id} rests on evidence this agent did not retrieve.")
                    continue
            if not evidence:
                rejected.append(f"A draft payroll conclusion ({claim_id}) was withheld: it cited no evidence retrieved in this task.")
                continue
            prose = draft.conclusion + " " + draft.proposed_action + " " + draft.title
            if MONEY_IN_PROSE.search(prose):
                rejected.append(f"A draft payroll conclusion ({claim_id}) was withheld: amounts must come from the calculation engine, not the narrative.")
                continue
            if draft.disposition not in {"substantiated", "cleared", "explained"}:
                rejected.append(f"A draft payroll conclusion ({claim_id}) was withheld: unrecognised disposition.")
                continue
            if draft.disposition == "substantiated" and calculation is None:
                rejected.append(f"A draft payroll conclusion ({claim_id}) was withheld: a substantiated payroll finding needs a deterministic calculation.")
                continue
            disposition = draft.disposition
            if disposition == "substantiated" and calculation is not None and calculation.category == "none":
                # The engine, not the narrative, decides whether there is an exception:
                # a calculation that found none cannot substantiate one.
                disposition = "cleared"
            try:
                claims.append(Claim(
                    id=claim_id, event_key=(draft.event_key.strip() or claim_id)[:200],
                    title=draft.title.strip()[:200] or claim_id,
                    conclusion=draft.conclusion.strip()[:2000] or "No conclusion text was returned.",
                    disposition=disposition, evidence_ids=evidence,
                    calculation_id=draft.calculation_id if calculation is not None else None,
                    proposed_action=draft.proposed_action.strip()[:1000] or "No financial change proposed.",
                ))
            except ValidationError:
                rejected.append(f"A draft payroll conclusion ({claim_id}) was withheld: it did not satisfy the claim contract.")
                continue
            seen.add(claim_id)
        return claims, rejected

    _SELECT_INSTRUCTION = (
        "Choose the sources and deterministic calculations that can settle this payroll task. "
        "Use only IDs listed in this message; never invent one. Prefer a calculation over reasoning about an amount "
        "yourself. Every calculation you choose also needs its 'requires_sources' read, and each read and each "
        "calculation costs one of the 'evidence_calls_available' allowed here, so stay within that total. "
        "Prioritise calculations that could expose an allocation exception over ones that only restate a total: "
        "unsupported allocation, ceiling excess, service outside an award window and unknown award references "
        "come before gross-to-net and expense totals. "
        "Always include the award, policy and service documents that are in scope. They state the criterion an "
        "allocation has to meet, and an amount tested against no criterion supports no conclusion; a service or "
        "timesheet document is also the only thing that can show whether a recorded split reflects actual work. "
        "If auditor_feedback is present, select only what answers that specific challenge. "
        "State the focus in one sentence, without any amount."
    )

    _FINDINGS_INSTRUCTION = (
        "Draw conclusions strictly from the evidence and calculations in this message. "
        "Cite source IDs only from 'evidence', and a calculation ID only from 'calculations'. "
        "Use disposition 'substantiated' only with a calculation ID; use 'explained' for a supported observation "
        "with no amount, and 'cleared' when the evidence resolves a concern. "
        "Write no currency amount, arithmetic result or percentage anywhere: reference the calculation ID and the "
        "renderer inserts the authoritative number. "
        "event_key should identify the underlying economic event so other agents reach the same key, for example "
        "record ID plus issue family plus period. "
        "A reclassification between funds leaves institution-wide payroll and cash unchanged; say so rather than "
        "implying recovered cash. Missing support is an evidence_request, not a finding. "
        "Propose actions for an authorized human; never state anything was approved, paid or applied. "
        "If auditor_feedback is present, return the complete revised result, keeping conclusions that remain supported."
    )


def _attempt_budget(tools, retry: bool) -> int:
    """Evidence calls to spend now, keeping a reserve for a post-challenge retry."""
    remaining = getattr(tools, "remaining", MIN_ATTEMPT_BUDGET)
    if retry or remaining <= MIN_ATTEMPT_BUDGET:
        return remaining
    return max(MIN_ATTEMPT_BUDGET, int(remaining * FIRST_ATTEMPT_SHARE))


def _unique(values: list[str]) -> list[str]:
    """Order-preserving de-duplication, so retries and reports stay stable."""
    seen, result = set(), []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
