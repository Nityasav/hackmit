"""Shared test inputs and test doubles. Nothing here is importable by the app.

`SAMPLE_FILES` is the small CSV/Markdown pack the intake tests upload through the
real import endpoints, so every number a test asserts is one the engine computed
from bytes a test supplied.

The classes below are minimal stand-ins for the ports in `app.cfo.ports`, so the
coordinator can be exercised without a model provider. They exist only to satisfy
an injected interface in a test; the application ships no scripted agent.
"""

from app.accounting.money import split_amount
from app.cfo.schemas import (
    Calculation, CalculationSpec, Claim, FollowUp, Narrative, NarrativeItem,
    Plan, Review, Scope, Source, SourceSpan, TaskSpec, WorkerResult,
)

# The intake pack, in a fixed order the intake tests index into.
SAMPLE_FILES = [
    {
        "name": "chart.csv",
        "role": "chart",
        "content": "account,name,type,report_mapping,effective_from\n"
                   "1000,Cash,asset,cash,2026-01-01\n"
                   "3000,Opening equity,equity,equity,2026-01-01\n"
                   "5000,Salary expense,expense,payroll,2026-01-01\n",
    },
    {
        "name": "opening.csv",
        "role": "opening",
        "content": "record_id,account,balance_date,debit,credit\n"
                   "OPEN-1,1000,2026-09-01,20000.00,0.00\n"
                   "OPEN-2,3000,2026-09-01,0.00,20000.00\n",
    },
    {
        "name": "ledger.csv",
        "role": "ledger",
        "content": "entry_id,line_id,date,account,debit,credit,award_id\n"
                   "PAY-1,1,2026-09-15,5000,10000.00,0.00,GRANT-1\n"
                   "PAY-1,2,2026-09-15,1000,0.00,10000.00,\n",
    },
    {
        "name": "payroll.csv",
        "role": "payroll",
        "content": "record_id,employee_id,service_start,service_end,pay_date,gross,deductions,net,"
                   "employer_cost,award_id,award_amount,ledger_entry_id,ledger_line_id\n"
                   "PAY-1,EMP-01,2026-09-01,2026-09-30,2026-09-15,10000.00,0.00,10000.00,0.00,"
                   "GRANT-1,10000.00,PAY-1,1\n",
    },
    {
        "name": "grants.csv",
        "role": "grants",
        "content": "award_id,name,ceiling,valid_from,valid_to\n"
                   "GRANT-1,Student support,50000.00,2026-09-01,2027-06-30\n",
    },
    {
        "name": "award-terms.md",
        "role": "policy",
        "content": "# Fictional Student Support Award\n"
                   "Award: GRANT-1\n"
                   "Valid: 2026-09-01 through 2027-06-30.\n"
                   "Shared staff costs require actual service records; budget percentages alone are not sufficient.\n"
                   "All entities and terms in this document are fictional.\n",
    },
    {
        "name": "service-record.md",
        "role": "service",
        "later": True,
        "content": "# Fictional service record\n"
                   "Employee: EMP-01\n"
                   "Payroll: PAY-1\n"
                   "Period: 2026-09-01 through 2026-09-30\n"
                   "Actual service allocation: 60% student support, 40% general operations.\n"
                   "Prepared as synthetic development evidence, not a record of a real institution.\n",
    },
]

# The two registers the transaction checks need, on top of the pack above.
TRANSACTION_FILES = [
    {
        "name": "invoices.csv",
        "role": "invoice",
        "content": "record_id,vendor_id,invoice_number,service_date,amount,po_id,receipt_id\n"
                   "INV-1,VENDOR-1,A-101,2026-09-10,1200.00,PO-1,\n"
                   "INV-2,VENDOR-1,A-101,2026-09-10,1200.00,PO-1,\n"
                   "INV-3,VENDOR-2,A-101,2026-09-10,1200.00,PO-2,REC-2\n",
    },
    {
        "name": "budget.csv",
        "role": "budget",
        "content": "record_id,account,amount,approval_reference\n"
                   "BUD-1,5000,9000.00,BOARD-DEMO-SEP\n",
    },
]


def sample_files(later=False):
    """The intake pack; `later` includes the withheld service record."""
    return [f for f in SAMPLE_FILES if later or not f.get("later")]


def withheld_service_record():
    return next(f for f in SAMPLE_FILES if f.get("later"))


class FixtureData:
    """A `DataSource` over three fixed spans, so engine tests need no provider.

    Every amount still comes out of `app.accounting.money`, not a literal, so the
    coordinator's calculation checks are exercised for real.
    """

    def __init__(self, award_share: int = 60, missing_service: bool = False):
        if not 0 <= award_share <= 100:
            raise ValueError("Award share must be between zero and one hundred.")
        self.award_share, self.missing_service = award_share, missing_service
        self.snapshot_id = f"TEST-{award_share}-{'missing' if missing_service else 'complete'}"

    async def snapshot(self, workspace):
        sources = [Source(id="payroll", title="Payroll entry", locator="payroll.csv row 2", domain="py"),
                   Source(id="award", title="Grant allocation terms", locator="award.md section 4.2", domain="gr")]
        if not self.missing_service:
            sources.append(Source(id="service", title="Current service record", locator="service.csv row 2", domain="shared"))
        calculations = [] if self.missing_service else [CalculationSpec(
            id="payroll-allocation",
            description="Reperform the payroll fund allocation from the current service record.",
            source_ids=["payroll", "award", "service"])]
        return Scope(workspace=workspace, snapshot_id=self.snapshot_id, institution="Test fixture school",
                     period="September", accounting_profile="Simplified accrual; USD integer cents",
                     sources=sources, calculations=calculations)

    async def read_source(self, scope, source_id):
        sources = {s.id: s for s in (await self.snapshot(scope.workspace)).sources}
        source = sources[source_id]
        text = {"payroll": "PAY-104: salary expense 1000000 cents; charged entirely to student-support award.",
                "award": "Shared staff costs must follow current service records. Budget percentages alone are insufficient.",
                "service": f"PAY-104 current service: award {self.award_share}%, general operations {100 - self.award_share}%."}[source_id]
        return SourceSpan(id=source_id, snapshot_id=self.snapshot_id, text=text, locator=source.locator)

    async def calculate(self, scope, calculation_id):
        if calculation_id != "payroll-allocation" or self.missing_service:
            raise ValueError("Calculation lacks required service evidence.")
        _, general = split_amount(1_000_000, [self.award_share, 100 - self.award_share])
        return Calculation(id=calculation_id, snapshot_id=self.snapshot_id, source_ids=["payroll", "award", "service"],
                           amount_cents=general, cash_delta_cents=0, category="reclassification",
                           description="Move unsupported award allocation to general operations; cash is unchanged.")


class StubPlanner:
    """A `CFOModel` that plans a fixed two-task DAG and echoes accepted claims."""

    label = "test-double/planner"

    async def plan(self, objective, scope):
        ids = [s.id for s in scope.sources]
        return Plan(rationale="Check the award criterion before preparing the payroll conclusion.", tasks=[
            TaskSpec(id="terms", role="gr", objective="Identify required payroll allocation evidence.", source_ids=["award"],
                     success_criteria="Cite the award clause and distinguish service evidence from budget assumptions."),
            TaskSpec(id="allocation", role="py", objective="Check payroll allocation against current service evidence.",
                     source_ids=ids, depends_on=["terms"],
                     success_criteria="Return a cited deterministic calculation or a targeted evidence request."),
        ])

    async def follow_up(self, task, claim, review):
        return FollowUp(action="request_evidence" if review.verdict == "needs_evidence" else "retry",
                        instruction=review.required_action or review.rationale)

    async def synthesize(self, run):
        return Narrative(items=[NarrativeItem(claim_id=a.claim.id, explanation=a.claim.conclusion,
                                              proposed_next_step=a.claim.proposed_action) for a in run.accepted])


class StubSpecialist:
    """A `Specialist` that reads what it cites, so the coordinator's gate is real."""

    async def investigate(self, task, scope, tools, dependencies, feedback):
        if task.role == "gr":
            await tools.read_source("award")
            return WorkerResult(summary="Read award criteria.", claims=[Claim(
                id="award-criterion", event_key="award-service-requirement", title="Service evidence is required",
                conclusion="Current service records are required to support shared payroll allocations.",
                disposition="explained", evidence_ids=["award"],
                proposed_action="Obtain the current service record before correcting payroll.")])
        if task.role == "py":
            if "service" not in {s.id for s in scope.sources}:
                return WorkerResult(summary="Current service record unavailable.",
                                    evidence_requests=["Provide the current payroll service record; a budget split is insufficient."])
            for source in ["payroll", "award", "service"]:
                await tools.read_source(source)
            await tools.calculate("payroll-allocation")
            return WorkerResult(summary="Computed payroll allocation using the deterministic engine.", claims=[Claim(
                id="payroll-reclass", event_key="PAY-104-allocation", title="Payroll fund allocation requires correction",
                conclusion="The recorded award charge exceeds the allocation supported by the current service record.",
                disposition="substantiated", evidence_ids=["payroll", "award", "service"], calculation_id="payroll-allocation",
                proposed_action="Submit a balanced reclassification proposal to the authorized human reviewer.")])
        return WorkerResult(summary="No AP records are supplied to this fixture.",
                            evidence_requests=["Provide AP records for investigation."])


class StubAuditor:
    """An `Auditor` that independently retrieves every citation before accepting."""

    async def review(self, claim, scope, tools):
        for source_id in claim.evidence_ids:
            await tools.read_source(source_id)
        if claim.calculation_id:
            await tools.calculate(claim.calculation_id)
        return Review(verdict="accept",
                      rationale="Independently retrieved the cited evidence and repeated the calculation, where present.")
