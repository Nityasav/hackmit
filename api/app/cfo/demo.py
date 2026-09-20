"""Explicitly SCRIPTED integration harness. Never used as live agent behavior.

These small adapters demonstrate the ports while Linda and Maxim work independently.
No hidden evaluator truth is available through the data or tool interfaces.
"""

from ..accounting.money import split_amount
from .schemas import Calculation, CalculationSpec, Claim, FollowUp, Narrative, NarrativeItem, Plan, Review, Scope, Source, SourceSpan, TaskSpec, WorkerResult


class DemoData:
    def __init__(self, award_share: int = 60, missing_service: bool = False):
        if not 0 <= award_share <= 100:
            raise ValueError("Award share must be between zero and one hundred.")
        self.award_share, self.missing_service = award_share, missing_service
        self.snapshot_id = f"SCRIPTED-{award_share}-{'missing' if missing_service else 'complete'}"

    async def snapshot(self, workspace):
        if workspace != "sandbox":
            raise ValueError("Scripted adapter supports sandbox only; MIT needs a real data adapter.")
        sources = [Source(id="payroll", title="Payroll entry", locator="payroll.csv row 2", domain="py"),
                   Source(id="award", title="Grant allocation terms", locator="award.md section 4.2", domain="gr")]
        if not self.missing_service:
            sources.append(Source(id="service", title="Current service record", locator="service.csv row 2", domain="shared"))
        return Scope(workspace=workspace, snapshot_id=self.snapshot_id, institution="Fictional CFO integration sandbox",
                     period="September", accounting_profile="Simplified accrual; USD integer cents", sources=sources,
                     calculations=[] if self.missing_service else [CalculationSpec(id="payroll-allocation",
                         description="Reperform the payroll fund allocation from the current service record.", source_ids=["payroll", "award", "service"])])

    async def read_source(self, scope, source_id):
        sources = {s.id: s for s in (await self.snapshot(scope.workspace)).sources}
        source = sources[source_id]
        text = {"payroll": "PAY-104: salary expense 1000000 cents; charged entirely to student-support award.",
                "award": "Shared staff costs must follow current service records. Budget percentages alone are insufficient.",
                "service": f"PAY-104 current service: award {self.award_share}%, general operations {100-self.award_share}%."}[source_id]
        return SourceSpan(id=source_id, snapshot_id=self.snapshot_id, text=text, locator=source.locator)

    async def calculate(self, scope, calculation_id):
        if calculation_id != "payroll-allocation" or self.missing_service:
            raise ValueError("Calculation lacks required service evidence.")
        _, general = split_amount(1_000_000, [self.award_share, 100-self.award_share])
        return Calculation(id=calculation_id, snapshot_id=self.snapshot_id, source_ids=["payroll", "award", "service"],
                           amount_cents=general, cash_delta_cents=0, category="reclassification",
                           description="Move unsupported award allocation to general operations; cash is unchanged.")


class ScriptedCFO:
    label = "scripted/integration-harness"

    async def plan(self, objective, scope):
        ids = [s.id for s in scope.sources]
        return Plan(rationale="Scripted plan: check award criterion before preparing the payroll conclusion.", tasks=[
            TaskSpec(id="terms", role="gr", objective="Identify required payroll allocation evidence.", source_ids=["award"],
                     success_criteria="Cite the award clause and distinguish service evidence from budget assumptions."),
            TaskSpec(id="allocation", role="py", objective="Check payroll allocation against current service evidence.", source_ids=ids,
                     depends_on=["terms"], success_criteria="Return a cited deterministic calculation or a targeted evidence request."),
        ])

    async def follow_up(self, task, claim, review):
        return FollowUp(action="request_evidence" if review.verdict == "needs_evidence" else "retry", instruction=review.required_action or review.rationale)

    async def synthesize(self, run):
        return Narrative(items=[NarrativeItem(claim_id=a.claim.id, explanation=a.claim.conclusion,
                                              proposed_next_step=a.claim.proposed_action) for a in run.accepted])


class ScriptedSpecialist:
    async def investigate(self, task, scope, tools, dependencies, feedback):
        if task.role == "gr":
            await tools.read_source("award")
            return WorkerResult(summary="Read award criteria.", claims=[Claim(
                id="award-criterion", event_key="award-service-requirement", title="Service evidence is required",
                conclusion="Current service records are required to support shared payroll allocations.",
                disposition="explained", evidence_ids=["award"], proposed_action="Obtain the current service record before correcting payroll.")])
        if task.role == "py":
            if "service" not in {s.id for s in scope.sources}:
                return WorkerResult(summary="Current service record unavailable.", evidence_requests=["Provide the current payroll service record; a budget split is insufficient."])
            for source in ["payroll", "award", "service"]:
                await tools.read_source(source)
            await tools.calculate("payroll-allocation")
            return WorkerResult(summary="Computed payroll allocation using the deterministic engine.", claims=[Claim(
                id="payroll-reclass", event_key="PAY-104-allocation", title="Payroll fund allocation requires correction",
                conclusion="The recorded award charge exceeds the allocation supported by the current service record.",
                disposition="substantiated", evidence_ids=["payroll", "award", "service"], calculation_id="payroll-allocation",
                proposed_action="Submit a balanced reclassification proposal to the authorized human reviewer.")])
        return WorkerResult(summary="No scripted AP records are supplied.", evidence_requests=["Provide AP records for investigation."])


class ScriptedAuditor:
    async def review(self, claim, scope, tools):
        for source_id in claim.evidence_ids:
            await tools.read_source(source_id)
        if claim.calculation_id:
            await tools.calculate(claim.calculation_id)
        return Review(verdict="accept", rationale="Scripted harness independently retrieved the cited evidence and repeated the calculation, where present.")
