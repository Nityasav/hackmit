"""Shared test inputs and test doubles. Nothing here is importable by the app.

`SAMPLE_FILES` is the small CSV/Markdown pack the intake tests upload through the
real import endpoints, so every number a test asserts is one the engine computed
from bytes a test supplied.

The classes below are minimal stand-ins for the ports in `app.cfo.ports`, so the
coordinator can be exercised without a model provider. They exist only to satisfy
an injected interface in a test; the application ships no scripted agent.
"""

import json

from app.accounting.money import split_amount
from app.cfo.schemas import (
    Calculation, CalculationSpec, Claim, FollowUp, Narrative, NarrativeItem,
    Plan, Review, Scope, Source, SourceSpan, TaskSpec, WorkerResult,
)

# The intake pack, in a fixed order the intake tests index into. One small, coherent
# period of a fictional SaaS company: a bill matched to its order and receipt and then
# paid, a customer invoice collected, the bank lines for both, and the policy the
# controls tests measure against. Every amount a test asserts is computed by the engine
# from these bytes, never written into the assertion.
SAMPLE_FILES = [
    {
        "name": "chart.csv",
        "role": "chart",
        "content": "account,name,type,report_mapping,effective_from\n"
                   "1000,Cash,asset,cash,2026-01-01\n"
                   "1100,Accounts receivable,asset,receivables,2026-01-01\n"
                   "2000,Accounts payable,liability,payables,2026-01-01\n"
                   "3100,Retained earnings,equity,equity,2026-01-01\n"
                   "4100,Services revenue,revenue,revenue,2026-01-01\n"
                   "6100,Cloud hosting,expense,opex,2026-01-01\n",
    },
    {
        "name": "opening.csv",
        "role": "opening",
        "content": "record_id,account,balance_date,debit,credit\n"
                   "OPEN-1,1000,2026-09-01,20000.00,0.00\n"
                   "OPEN-2,3100,2026-09-01,0.00,20000.00\n",
    },
    {
        "name": "ledger.csv",
        "role": "ledger",
        "content": "entry_id,line_id,date,account,debit,credit,event_ref\n"
                   "JE-1,1,2026-09-08,6100,1200.00,0.00,EVT-1\n"
                   "JE-1,2,2026-09-08,2000,0.00,1200.00,EVT-1\n"
                   "JE-2,1,2026-09-24,2000,1200.00,0.00,EVT-1\n"
                   "JE-2,2,2026-09-24,1000,0.00,1200.00,EVT-1\n"
                   "JE-3,1,2026-09-05,1100,4000.00,0.00,EVT-2\n"
                   "JE-3,2,2026-09-05,4100,0.00,4000.00,EVT-2\n"
                   "JE-4,1,2026-09-27,1000,4000.00,0.00,EVT-2\n"
                   "JE-4,2,2026-09-27,1100,0.00,4000.00,EVT-2\n",
    },
    {
        "name": "vendors.csv",
        "role": "vendors",
        "content": "vendor_id,name,country,payment_terms_days\n"
                   "V-1,Northlight Systems,US,15\n"
                   "V-2,Kestrel Labs,US,30\n",
    },
    {
        "name": "purchase_orders.csv",
        "role": "purchase_orders",
        "content": "po_id,line_id,vendor_id,description,order_date,amount,approver,event_ref\n"
                   "PO-1,1,V-1,Cloud hosting,2026-09-02,1200.00,Amara Abara,EVT-1\n",
    },
    {
        "name": "goods_receipts.csv",
        "role": "goods_receipts",
        "content": "receipt_id,line_id,po_id,po_line_id,received_date,amount,event_ref\n"
                   "GR-1,1,PO-1,1,2026-09-06,1200.00,EVT-1\n",
    },
    {
        "name": "vendor_invoices.csv",
        "role": "vendor_invoices",
        "content": "record_id,vendor_id,invoice_number,invoice_date,due_date,amount,po_id,receipt_id,event_ref\n"
                   "VI-1,V-1,INV-100,2026-09-08,2026-09-23,1200.00,PO-1,GR-1,EVT-1\n"
                   "VI-2,V-2,INV-200,2026-09-18,2026-10-18,850.00,,,EVT-3\n",
    },
    {
        "name": "payments.csv",
        "role": "payments",
        "content": "payment_id,vendor_id,payment_date,method,amount,reference,invoice_number,event_ref\n"
                   "PMT-1,V-1,2026-09-24,ach,1200.00,ACH-5001,INV-100,EVT-1\n",
    },
    {
        "name": "customers.csv",
        "role": "customers",
        "content": "customer_id,name,country,payment_terms_days\n"
                   "C-1,Ashgrove Holdings,US,30\n",
    },
    {
        "name": "customer_invoices.csv",
        "role": "customer_invoices",
        "content": "record_id,customer_id,invoice_number,invoice_date,due_date,amount,event_ref\n"
                   "CI-1,C-1,SI-300,2026-09-05,2026-10-05,4000.00,EVT-2\n",
    },
    {
        "name": "remittances.csv",
        "role": "remittances",
        "content": "remittance_id,customer_id,received_date,amount,reference,invoice_refs,event_ref\n"
                   "RM-1,C-1,2026-09-27,4000.00,WIRE-7001,SI-300,EVT-2\n",
    },
    {
        "name": "bank_transactions.csv",
        "role": "bank_transactions",
        "content": "bank_id,bank_account,settlement_date,direction,amount,description,bank_reference,event_ref\n"
                   "BK-1,Operating,2026-09-24,out,1200.00,ACH DEBIT NORTHLIGHT,ACH-5001,EVT-1\n"
                   "BK-2,Operating,2026-09-27,in,4000.00,WIRE CREDIT ASHGROVE,WIRE-7001,EVT-2\n",
    },
    {
        "name": "approvals.csv",
        "role": "approvals",
        # A different person from the one who raised PO-1, so the segregation-of-duties
        # test has a clean case to pass on as well as a breach to find.
        "content": "record_id,actor,authority,action,target_type,target_id,approved_at,event_ref\n"
                   "AP-1,Bo Baptiste,Finance director,approve_invoice,vendor_invoice,VI-1,2026-09-09,EVT-1\n",
    },
    {
        "name": "expense-policy.md",
        "role": "policy",
        "content": "# Fictional expense and approval policy\n"
                   "Purchases up to 5,000.00 USD: department lead.\n"
                   "An invoice without a purchase order is held for review.\n"
                   "No person may approve a payment to a counterparty they requested.\n"
                   "All entities and terms in this document are fictional.\n",
    },
    {
        "name": "delivery-note.md",
        "role": "document",
        "later": True,
        "content": "# Fictional delivery note\n"
                   "Order: PO-1\n"
                   "Receipt: GR-1\n"
                   "Accepted: 2026-09-06\n"
                   "Prepared as synthetic development evidence, not a record of a real company.\n",
    },
]

# The extra registers the transaction checks need, on top of the pack above. The two
# bills share a vendor, number and amount, which is what an exact-key duplicate test
# looks for; the third differs by vendor and must not be swept up with them.
TRANSACTION_FILES = [
    {
        "name": "more_invoices.csv",
        "role": "vendor_invoices",
        "source_system": "duplicates",
        "content": "record_id,vendor_id,invoice_number,invoice_date,due_date,amount\n"
                   "VI-10,V-1,A-101,2026-09-10,2026-09-25,1200.00\n"
                   "VI-11,V-1,A-101,2026-09-10,2026-09-25,1200.00\n"
                   "VI-12,V-2,A-101,2026-09-10,2026-10-10,1200.00\n",
    },
    {
        "name": "budgets.csv",
        "role": "budgets",
        "content": "record_id,account,period,amount,approval_reference\n"
                   "BU-1,6100,2026-09,900.00,BOARD-2026-01\n",
    },
]


# --------------------------------------------------------------------------- #
# Shared intake helpers
# --------------------------------------------------------------------------- #
#
# These lived in `test_cfo_intake.py` and were imported by six other test modules,
# which meant deleting a test file broke unrelated suites. Shared scaffolding belongs
# here; a test module should only contain tests.

SAMPLE = {"files": SAMPLE_FILES}
HEADERS = {"X-SchoolTrace-Reviewer": "local-reviewer"}


def commit_pack(client, later=False):
    """Create a workspace and commit the sample pack.

    `later` includes the withheld delivery note, which is how a test gets a second
    snapshot with one more record in it.
    """
    ws = client.post("/api/workspaces", json={
        "name": "Fictional SaaS company", "start": "2026-09-01",
        "end": "2026-09-30", "scope": "September close",
    }).json()["id"]
    files = [f for f in SAMPLE["files"] if later or not f.get("later")]
    batch = client.post(
        f"/api/workspaces/{ws}/imports",
        files=[("files", (f["name"], f["content"].encode(), "text/plain")) for f in files],
        data={"metadata": json.dumps([{"role": f["role"], **f.get("options", {})} for f in files])},
    ).json()
    saved = client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/commit",
                        json={"expected_version": batch["version"], "idempotency_key": batch["id"]})
    assert saved.status_code == 200, saved.text
    return ws


def sample(role):
    """One pack file by role. Tests name what they mean instead of indexing a
    position, so reordering or extending the pack cannot silently retarget a test."""
    return next(f for f in SAMPLE_FILES if f["role"] == role)


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

    def __init__(self, award_share: int = 60, missing_service: bool = False, precedents=()):
        if not 0 <= award_share <= 100:
            raise ValueError("Award share must be between zero and one hundred.")
        self.award_share, self.missing_service = award_share, missing_service
        self.snapshot_id = f"TEST-{award_share}-{'missing' if missing_service else 'complete'}"
        self.precedents = list(precedents)
        #: Every (workspace, ids) the engine counted, so a test can assert the
        #: coordinator recorded a use without reaching into the database.
        self.noted_uses: list[tuple[str, list[str]]] = []

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
                     sources=sources, calculations=calculations, precedents=list(self.precedents))

    async def note_precedent_uses(self, workspace, precedent_ids):
        self.noted_uses.append((workspace, list(precedent_ids)))

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
        return Plan(memory_checks=[], rationale="Check the award criterion before preparing the payroll conclusion.", tasks=[
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

# --------------------------------------------------------------------------- #
# Triage-agent doubles
# --------------------------------------------------------------------------- #
#
# A scripted Responses client, so the triage boundary can be exercised without a
# provider. It replays one fixed sequence: read the workspace context, read a span
# of the policy, then submit an analysis citing that exact span. The agent under
# test is rebuilt in phase 2, and these move with it.

from types import SimpleNamespace


def committed_workspace(client):
    response = client.post("/api/workspaces", json={
        "name": "Fictional SaaS company", "start": "2026-09-01", "end": "2026-09-30", "scope": "September close",
    })
    ws = response.json()["id"]
    files = [f for f in SAMPLE["files"] if not f.get("later")]
    staged = client.post(
        f"/api/workspaces/{ws}/imports",
        files=[("files", (f["name"], f["content"].encode(), "text/plain")) for f in files],
        data={"metadata": json.dumps([{"role": f["role"]} for f in files])},
    ).json()
    committed = client.post(f"/api/workspaces/{ws}/imports/{staged['id']}/commit", json={
        "expected_version": staged["version"], "idempotency_key": staged["id"] + ":1",
    })
    assert committed.status_code == 200, committed.text
    return ws, committed.json()["snapshot_id"]


def function_call(name, arguments, call_id):
    return SimpleNamespace(type="function_call", name=name, arguments=json.dumps(arguments), call_id=call_id)


class FakeResponses:
    def __init__(self):
        self.step = 0
        self.source_id = None

    def create(self, **kwargs):
        assert kwargs["store"] is False
        assert kwargs["parallel_tool_calls"] is False
        if self.step == 0:
            output = [function_call("get_workspace_context", {}, "call-1")]
        elif self.step == 1:
            tool_result = json.loads(kwargs["input"][-1]["output"])
            self.source_id = next(source["source_id"] for source in tool_result["result"]["sources"] if source["role"] == "policy")
            output = [function_call("read_source_span", {
                "source_id": self.source_id, "start_line": 4, "end_line": 4,
            }, "call-2")]
        else:
            output = [function_call("submit_cfo_analysis", {
                "memory_checks": [], "executive_briefing": "The supplied award terms require service evidence before allocation support can be assessed.",
                "scope_assessed": "September close within the committed synthetic snapshot.",
                "limitations": ["Population completeness is not verified."],
                "findings": [{
                    "title": "Service evidence needs review", "status": "needs_evidence",
                    "summary": "The award terms specify actual service records for shared staff costs.",
                    "citations": [{"source_id": self.source_id, "line": 4,
                                   "quote": "Shared staff costs require actual service records"}],
                    "limitations": ["No conclusion on allocation allowability has been reached."],
                }],
                "evidence_requests": [{"title": "September service record", "role": "document",
                                       "reason": "Test the allocation against actual service."}],
                "next_tasks": [{"specialist": "grants_compliance", "title": "Test grant allocation support",
                                "objective": "Compare payroll allocation to award terms and service evidence."}],
            }, "call-3")]
        self.step += 1
        return SimpleNamespace(output=output, usage=SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15))

    def close(self):
        pass
