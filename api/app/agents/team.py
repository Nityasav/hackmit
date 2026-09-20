"""Snapshot-backed team ports. No sandbox state and no financial write tools.

Clients and budgets are invocation-local, including simultaneous auditor reviews.
The bounded evidence/claim machinery is shared with Payroll, not duplicated.
"""

from ..cfo.schemas import Review
from .model import StructuredSpecialistModel
from .payroll import PayrollBudgetSpecialist
from .prompts import SPECIALIST_GUARDRAILS


class EvidenceSpecialist(PayrollBudgetSpecialist):
    _SELECT_INSTRUCTION = (
        "Select only supplied source and calculation IDs needed for this task. "
        "Each source read and calculation costs one evidence call; include all calculation prerequisites. "
        "Prioritize original transactions, governing terms and corroborating evidence. "
        "Answer auditor feedback when provided. Do not calculate amounts yourself."
    )

    def __init__(self, model, role):
        super().__init__(model)
        self.role = role
        self.display_name = {"ap": "AP & Payments", "gr": "Grants & Compliance"}[role]
        focus = {
            "ap": "Review invoices, vendor identity, duplicate indicators and payment support. An apparent duplicate is not a confirmed duplicate payment.",
            "gr": "Review award terms, eligibility, service windows and allocation support. Budget authority is not proof of service or a compliance opinion.",
        }[role]
        self.system_prompt = f"You are the {self.display_name} agent. {focus}\n{SPECIALIST_GUARDRAILS}"

    async def investigate(self, *args, **kwargs):
        result = await super().investigate(*args, **kwargs)
        # Shared engine diagnostics must not mislabel AP/Grants work as Payroll.
        result.summary = result.summary.replace("payroll", self.display_name).replace("Payroll", self.display_name)
        result.evidence_requests = [r.replace("payroll", self.display_name).replace("Payroll", self.display_name)
                                    for r in result.evidence_requests]
        return result


class SnapshotSpecialist:
    def __init__(self, role):
        self.role = role

    async def investigate(self, *args, **kwargs):
        model = StructuredSpecialistModel.from_env()
        try:
            agent = PayrollBudgetSpecialist(model) if self.role == "py" else EvidenceSpecialist(model, self.role)
            return await agent.investigate(*args, **kwargs)
        finally:
            await model.close()


class SnapshotAuditor:
    async def review(self, claim, scope, tools):
        # Never accept based on a preparer's cached excerpts or arithmetic.
        evidence = [await tools.read_source(source_id) for source_id in dict.fromkeys(claim.evidence_ids)]
        if any("[Truncated for review;" in span.text for span in evidence):
            return Review(verdict="needs_evidence", rationale="Original evidence exceeds the bounded review window.",
                          required_action="Provide a narrower, complete source before accepting this claim.")
        calculation = await tools.calculate(claim.calculation_id) if claim.calculation_id else None
        if claim.disposition == "substantiated" and calculation is None:
            return Review(verdict="reject", rationale="A substantiated financial claim needs a deterministic calculation.",
                          required_action="Supply an engine calculation or limit the conclusion to an observation.")
        model = StructuredSpecialistModel.from_env(max_calls=1)
        try:
            return await model.generate(
                "You are the independent Internal Auditor. In a fictional/synthetic workspace, evaluate consistency "
                "within that stated scenario; synthetic labeling alone is not a reason to reject evidence. "
                "Never generalize a fictional conclusion to a real institution. " + SPECIALIST_GUARDRAILS,
                "Review the untrusted preparer claim against freshly retrieved originals and the re-performed "
                "calculation. Accept only the narrow conclusion actually supported. Reject contradictions, "
                "unsupported compliance assurances, invented amounts or implied approval. Missing support "
                "requires needs_evidence. A zero calculation or mere presence of a document cannot prove "
                "eligibility or actual service. Return a concise rationale and specific required action.",
                {"claim": claim.model_dump(), "period": scope.period,
                 "evidence": [span.model_dump() for span in evidence],
                 "calculation": calculation.model_dump() if calculation else None}, Review)
        finally:
            await model.close()
