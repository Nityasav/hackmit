"""The phase-2 gate: A1 processes one invoice, cites its evidence, respects its cap.

No provider is called. `FakeModel` replays a scripted tool-calling exchange, so what is
being tested is the runtime's guarantees rather than a model's behaviour: scope,
budget, citation validation, computed confidence and escalation.

The deterministic half — matching, duplicates, policy — is tested directly against
records, because it is arithmetic and deserves to be checked as arithmetic.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app import db, ingestion
from app.accounting import match
from app.agents import budget as budget_module
from app.agents import schemas
from app.agents.budget import BudgetExceeded, Meter, cost_cents
from app.agents.registry import AGENTS, ancestry, children
from app.agents import runtime
from app.agents.runtime import AgentFailed, escalation_reasons, run_agent
from app.agents.tools import ScopeError, Toolbox
from tests.conftest import SAMPLE_FILES, sample


# --------------------------------------------------------------------------- #
# Scaffolding
# --------------------------------------------------------------------------- #

@pytest.fixture
def ws(tmp_path, monkeypatch) -> str:
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    created = ingestion.create_workspace(ingestion.WorkspaceCreate(
        name="Fictional SaaS company", start="2026-09-01", end="2026-09-30",
        scope="September close",
        settings={"approval_limit_cents": 500_000, "materiality_cents": 100_000},
    ))
    workspace = created["id"]
    files = [f for f in SAMPLE_FILES if not f.get("later")]
    batch = ingestion.stage(workspace, [
        (f["name"], f["content"].encode(), ingestion.FileOptions(role=f["role"]))
        for f in files])
    assert batch["status"] == "ready_to_commit", batch["issues"]
    ingestion.commit(workspace, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key="agents"))
    return workspace


def records_of(ws: str) -> list[dict]:
    return ingestion.financial_records(ws)["records"]


def invoice_key(ws: str, number: str) -> str:
    return next(r["record_key"] for r in records_of(ws)
                if r["role"] == "vendor_invoices" and r["payload"]["invoice_number"] == number)


class FakeModel:
    """A scripted Responses client. Each turn is (tool_calls, final_result).

    `build` lets one script serve several agents: the runtime asks each agent for that
    agent's own schema, so a fixed `APResult` handed to A2 fails validation and the agent
    retries until its budget is gone. A callable receives the requested schema and
    returns something valid for it.
    """

    def __init__(self, turns, usage=(1000, 200), build=None):
        self.turns, self.usage, self.build = list(turns), usage, build
        self.calls = 0
        #: Turns consumed per conversation. One client serves every agent in a graph
        #: run, and a single global counter meant the first agent ate the whole script
        #: and the rest got its leftovers — concluding without reading, so their
        #: citations were refused. Each conversation gets the script from the start.
        self._per_conversation: dict[str, int] = {}
        self.seen_tools: list[str] = []
        self.responses = self

    async def parse(self, **kwargs):
        self.calls += 1
        system = kwargs["input"][0].get("content", "") if kwargs.get("input") else ""
        turn = self._per_conversation.get(system, 0)
        self._per_conversation[system] = turn + 1
        tool_calls, final = self.turns[min(turn, len(self.turns) - 1)]
        # A turn may be a callable when the call it should make depends on which agent
        # is asking — each one may read a different set of roles.
        if callable(tool_calls):
            tool_calls = tool_calls(kwargs)
        output = [SimpleNamespace(type="function_call", name=name,
                                  arguments=json.dumps(args), call_id=f"c{i}")
                  for i, (name, args) in enumerate(tool_calls)]
        self.seen_tools += [name for name, _ in tool_calls]
        if not output and self.build is not None:
            final = self.build(kwargs.get("text_format"), kwargs)
        return SimpleNamespace(
            output=output, output_parsed=None if output else final,
            usage=SimpleNamespace(input_tokens=self.usage[0], output_tokens=self.usage[1]))


def ap_result(**overrides) -> schemas.APResult:
    base = dict(
        summary="The invoice matches its order and receipt.",
        disposition="clear",
        rationale="The billed amount agrees with the ordered and received amounts, and an "
                  "approval is recorded against it.",
        citations=[schemas.Citation(role="vendor_invoices", record_key="VI-1")],
        proposed_action="Release for payment in the next run.",
        # Required, not defaulted: an agent offered no precedent still has to
        # say so explicitly, so silence never reads as a completed check.
        memory_checks=[],
        may_pay=True)
    return schemas.APResult(**{**base, **overrides})


def run(ws, agent_id, objective, model, *, meter=None, record_keys=()):
    return asyncio.run(run_agent(
        ws, agent_id, objective, meter=meter or Meter(), thread_id="t-1",
        record_keys=record_keys, client=model))


# --------------------------------------------------------------------------- #
# Deterministic matching
# --------------------------------------------------------------------------- #

def test_a_fully_matched_invoice_scores_full_confidence(ws):
    result = match.three_way(records_of(ws), invoice_key(ws, "INV-100"),
                             ingestion.workspace_config(ws))

    assert result.confidence == 100, result.features
    assert result.codes == ()
    assert result.po_id == "PO-1" and result.receipt_id == "GR-1"


def test_confidence_is_reconstructible_from_its_own_features(ws):
    """The whole point of a rubric: someone can add it up by hand."""
    result = match.three_way(records_of(ws), invoice_key(ws, "INV-100"),
                             ingestion.workspace_config(ws))
    expected = sum(w for name, w in match.WEIGHTS.items() if result.features[name])

    assert result.confidence == expected
    assert set(result.features) == set(match.WEIGHTS)


def test_an_invoice_with_no_order_loses_exactly_the_weights_it_should(ws):
    result = match.three_way(records_of(ws), invoice_key(ws, "INV-200"),
                             ingestion.workspace_config(ws))

    assert "no_purchase_order" in result.codes
    assert "no_goods_receipt" in result.codes
    assert not result.features["purchase_order_found"]
    # It never guesses an order from amount and date; that is the human's judgment.
    assert result.po_id == ""
    assert result.confidence < 85


def test_an_unset_approval_limit_stands_the_test_down_instead_of_assuming_one(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    created = ingestion.create_workspace(ingestion.WorkspaceCreate(
        name="No limit set", start="2026-09-01", end="2026-09-30", scope="close"))
    workspace = created["id"]
    files = [f for f in SAMPLE_FILES if not f.get("later")]
    batch = ingestion.stage(workspace, [
        (f["name"], f["content"].encode(), ingestion.FileOptions(role=f["role"])) for f in files])
    ingestion.commit(workspace, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key="k"))

    result = match.three_way(records_of(workspace), invoice_key(workspace, "INV-100"),
                             ingestion.workspace_config(workspace))

    assert "approval_limit_unknown" in result.codes
    assert "over_approval_limit" not in result.codes


def test_duplicates_are_keyed_on_the_claim_not_on_the_rows_in_it():
    """A third matching invoice must not retire the finding and mint a new one."""
    first = match.duplicate_key("V-1", "A-101", 120_000, "USD")
    again = match.duplicate_key(" v-1 ", "A-101", 120_000, "USD")
    other = match.duplicate_key("V-2", "A-101", 120_000, "USD")

    assert first == again, "case and surrounding space must not change the identity"
    assert first != other


def test_exposure_counts_the_repeats_not_the_whole_group(ws):
    extra = next(f for f in __import__("tests.conftest", fromlist=["x"]).TRANSACTION_FILES
                 if f["role"] == "vendor_invoices")
    batch = ingestion.stage(ws, [(extra["name"], extra["content"].encode(),
                                  ingestion.FileOptions(role="vendor_invoices",
                                                        source_system="duplicates"))])
    ingestion.commit(ws, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key="dupes"))

    found = match.find_duplicates(records_of(ws))
    candidate = next(c for c in found if c["invoice_number"] == "A-101")

    assert candidate["count"] == 2
    assert candidate["exposure_cents"] == candidate["amount_cents"]
    assert "does not establish" in candidate["note"]


# --------------------------------------------------------------------------- #
# Budget
# --------------------------------------------------------------------------- #

def test_cost_is_integer_cents_rounded_up():
    """Rounding down is how a meter quietly overspends."""
    assert cost_cents("gpt-5.6-terra", 1_000_000, 0) == 200
    assert cost_cents("gpt-5.6-terra", 1, 0) == 1, "a fraction of a cent still costs a cent"
    assert cost_cents("gpt-5.6-luna", 0, 0) == 0


def test_an_unknown_model_is_priced_at_the_most_expensive_tier():
    """Misconfiguration must never be a way to spend without the meter noticing."""
    assert cost_cents("something-nobody-configured", 1_000_000, 0) == \
        cost_cents("gpt-5.6-sol", 1_000_000, 0)


def test_a_task_stops_at_its_own_budget(ws):
    spec = AGENTS["A1"]
    meter = Meter()
    for _ in range(spec.budget.model_calls):
        meter.check_model_call("A1", spec.model, spec.budget)
        meter.charge_model_call("A1", spec.model, 1000, 200)

    with pytest.raises(BudgetExceeded, match="model call"):
        meter.check_model_call("A1", spec.model, spec.budget)


def test_a_run_stops_at_its_cap_even_when_a_task_has_room(ws):
    spec = AGENTS["A1"]
    meter = Meter(run_cap_cents=1)

    with pytest.raises(BudgetExceeded, match="cap"):
        meter.check_model_call("A1", spec.model, spec.budget)


def test_evidence_calls_are_bounded_too(ws):
    """An agent that reads without concluding is a loop, not a cheap agent."""
    spec = AGENTS["A1"]
    meter = Meter()
    for _ in range(spec.budget.tool_calls):
        meter.charge_tool_call("A1", spec.budget)

    with pytest.raises(BudgetExceeded, match="evidence call"):
        meter.charge_tool_call("A1", spec.budget)


# --------------------------------------------------------------------------- #
# Scope
# --------------------------------------------------------------------------- #

def _toolbox(ws, agent_id="A1", meter=None, **kwargs):
    return Toolbox(ws, AGENTS[agent_id], meter or Meter(), records_of(ws),
                   ingestion.workspace_config(ws), "snap-1", "t-1", **kwargs)


def test_an_agent_cannot_read_a_role_it_never_declared(ws):
    box = _toolbox(ws)
    assert "vendor_invoices" in box.roles

    with pytest.raises(ScopeError, match="not among them"):
        box.read_records("customer_invoices")


def test_an_agent_cannot_use_a_tool_it_does_not_hold(ws):
    box = _toolbox(ws, "A4")  # cash management holds no matching tool
    with pytest.raises(ScopeError, match="does not hold"):
        box.three_way_match("anything")


def test_delegation_narrows_scope_and_can_never_widen_it(ws):
    parent = _toolbox(ws, "A")
    child = parent.narrow(AGENTS["A1"], record_keys=(invoice_key(ws, "INV-100"),))

    assert set(child.roles) <= set(parent.roles)
    assert set(child.roles) < set(parent.roles), "a delegation must actually narrow"
    # The parent covers its whole subtree by construction, so a child never needs
    # authority the delegator did not already hold.
    assert "purchase_orders" in parent.roles


def test_a_narrowed_box_cannot_reach_records_outside_the_delegation(ws):
    box = _toolbox(ws, record_keys=(invoice_key(ws, "INV-100"),))
    with pytest.raises(ScopeError, match="outside this delegation"):
        box.three_way_match(invoice_key(ws, "INV-200"))


def test_citing_a_source_the_agent_was_shown_is_allowed(ws):
    """The guard catches invention. It must not refuse evidence the agent was handed.

    `read_records` puts a source id in front of the agent for every row it returns, so
    citing one is citing what it saw. Recording only the record key made a live A1 run
    fail with "cited a source it did not read" on a citation that was entirely correct.
    """
    box = _toolbox(ws)
    shown = box.read_records("vendor_invoices")["records"][0]

    box.validate_citations([schemas.Citation(
        role="vendor_invoices", record_key=shown["record_key"],
        source_id=shown["source_id"])])


def test_citing_a_record_the_agent_never_read_is_refused(ws):
    box = _toolbox(ws)
    fabricated = [schemas.Citation(role="vendor_invoices", record_key="VI-999")]

    with pytest.raises(ScopeError, match="did not retrieve"):
        box.validate_citations(fabricated)


# --------------------------------------------------------------------------- #
# The gate: A1 end to end
# --------------------------------------------------------------------------- #

def test_a1_matches_an_invoice_cites_its_evidence_and_records_a_decision(ws):
    key = invoice_key(ws, "INV-100")
    model = FakeModel([
        ([("three_way_match", {"invoice_key": key})], None),
        ([], ap_result(citations=[
            schemas.Citation(role="vendor_invoices", record_key=key, note="the invoice"),
        ], matched_po="PO-1", matched_receipt="GR-1")),
    ])

    result = run(ws, "A1", f"Review invoice {key}.", model, record_keys=(key,))

    assert result.result.disposition == "clear"
    assert result.confidence == 100, "confidence comes from the rubric, not the model"
    assert not result.escalated
    assert result.cost_cents > 0, "a paid run must report what it cost"

    with db.connect() as connection:
        saved = connection.execute(
            "SELECT * FROM agent_decisions WHERE ws=? AND id=?", (ws, result.decision_id)
        ).fetchone()
    assert saved["agent"] == "A1" and saved["confidence"] == 100
    assert saved["cost_cents"] == result.cost_cents


def test_matching_draws_links_carrying_how_and_how_certainly(ws):
    key = invoice_key(ws, "INV-100")
    model = FakeModel([
        ([("three_way_match", {"invoice_key": key})], None),
        ([], ap_result(citations=[schemas.Citation(role="vendor_invoices", record_key=key)])),
    ])
    run(ws, "A1", "Match it.", model, record_keys=(key,))

    with db.connect() as connection:
        links = connection.execute(
            "SELECT * FROM links WHERE ws=? ORDER BY kind", (ws,)).fetchall()

    kinds = {link["kind"]: link for link in links}
    assert "matches_order" in kinds and "matches_receipt" in kinds
    assert kinds["matches_order"]["method"] == "exact"
    assert kinds["matches_order"]["confidence"] == 100
    assert kinds["matches_order"]["created_by"] == "A1"


def test_an_unmatched_invoice_escalates_on_its_named_conditions(ws):
    key = invoice_key(ws, "INV-200")
    model = FakeModel([
        ([("three_way_match", {"invoice_key": key})], None),
        ([], ap_result(
            disposition="exception",
            summary="The invoice has no order or receipt behind it.",
            rationale="Nothing recorded shows what was ordered or what was delivered.",
            exceptions=[schemas.Exception_(code="no_purchase_order",
                                           detail="No purchase order is named on the invoice.")],
            citations=[schemas.Citation(role="vendor_invoices", record_key=key)],
            may_pay=False)),
    ])

    result = run(ws, "A1", "Review it.", model, record_keys=(key,))

    assert result.escalated
    assert any("no_purchase_order" in reason for reason in result.escalation_reasons)
    assert any("confidence" in reason for reason in result.escalation_reasons)


def test_a_result_citing_evidence_it_never_retrieved_is_rejected(ws):
    key = invoice_key(ws, "INV-100")
    model = FakeModel([
        ([], ap_result(citations=[
            schemas.Citation(role="vendor_invoices", record_key="VI-DOES-NOT-EXIST")])),
    ])

    with pytest.raises(ScopeError, match="did not retrieve"):
        run(ws, "A1", "Review it.", model, record_keys=(key,))


def test_an_agent_whose_inputs_are_missing_says_so_instead_of_guessing(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    created = ingestion.create_workspace(ingestion.WorkspaceCreate(
        name="Nothing uploaded", start="2026-09-01", end="2026-09-30", scope="close"))
    workspace = created["id"]
    chart = sample("chart")
    batch = ingestion.stage(workspace, [(chart["name"], chart["content"].encode(),
                                         ingestion.FileOptions(role="chart"))])
    ingestion.commit(workspace, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key="k"))

    with pytest.raises(AgentFailed, match="needs data that has not been supplied"):
        run(workspace, "A1", "Review payables.", FakeModel([([], ap_result())]))


def test_the_runtime_stops_rather_than_returning_a_thinner_answer(ws):
    key = invoice_key(ws, "INV-100")
    # Every turn asks for another tool call and never concludes.
    model = FakeModel([([("three_way_match", {"invoice_key": key})], None)])

    with pytest.raises((AgentFailed, BudgetExceeded)):
        run(ws, "A1", "Loop forever.", model, record_keys=(key,))


# --------------------------------------------------------------------------- #
# Result schema
# --------------------------------------------------------------------------- #

def test_prose_may_not_contain_figures():
    with pytest.raises(ValueError, match="must not contain figures"):
        ap_result(rationale="The invoice is over by 1200.00 dollars.")


def test_an_exception_disposition_must_name_an_exception():
    with pytest.raises(ValueError, match="must name at least one"):
        ap_result(disposition="exception", exceptions=[])


def test_a_clear_disposition_cannot_also_list_exceptions():
    with pytest.raises(ValueError, match="cannot also list"):
        ap_result(disposition="clear",
                  exceptions=[schemas.Exception_(code="x", detail="y")],
                  citations=[schemas.Citation(role="vendor_invoices", record_key="k")])


def test_a_conclusion_must_cite_something():
    with pytest.raises(ValueError, match="must cite the evidence"):
        ap_result(citations=[])


def test_the_schema_has_no_confidence_field():
    """Confidence is computed. A model must have no way to assert one."""
    assert "confidence" not in schemas.AgentResult.model_fields
    assert "confidence" not in schemas.APResult.model_fields


# --------------------------------------------------------------------------- #
# Registry invariants
# --------------------------------------------------------------------------- #

def test_the_organization_is_the_one_the_spec_describes():
    assert len(AGENTS) == 22
    assert len(children("orchestrator")) == 4
    assert {c.id for c in children("A")} == {"A1", "A2", "A3", "A4"}
    assert {c.id for c in children("C")} == {"C1", "C2", "C3", "C4", "C5"}
    assert ancestry("A1") == ("A", "orchestrator")


def test_no_agent_reviews_itself_and_reviewers_are_independent():
    for spec in AGENTS.values():
        if spec.reviewer:
            assert spec.reviewer != spec.id
            assert spec.reviewer in {"B4", "D1", "D2"}


def test_statements_and_evidence_are_never_authored_by_a_model():
    """If asked whether a model wrote the balance sheet, the answer has to be no."""
    assert AGENTS["B3"].llm is False
    assert AGENTS["D3"].llm is False


def test_every_agent_reads_only_what_it_declared_it_needs():
    from app import requirements
    for spec in AGENTS.values():
        for role in spec.roles:
            assert any(requirements.BY_ID[r].role == role for r in spec.requires)


def test_a_child_can_never_outspend_its_parent_in_one_task():
    for spec in AGENTS.values():
        if spec.parent:
            assert spec.budget.usd_cents <= AGENTS[spec.parent].budget.usd_cents, spec.id


def test_escalation_reads_thresholds_from_the_spec_not_the_model():
    spec = AGENTS["A1"]
    result = ap_result(citations=[schemas.Citation(role="vendor_invoices", record_key="k")])

    assert escalation_reasons(spec, result, 100, 1_000) == ()
    assert escalation_reasons(spec, result, 84, 1_000)  # below the confidence threshold
    assert escalation_reasons(spec, result, 100, 500_000)  # at the amount that always escalates


def test_an_agent_that_can_score_and_did_not_does_not_pass_as_confident():
    """The hole this closes: a threshold is only consulted when a score exists, so the
    cheapest way past one was to skip the calculation it is measured against."""
    spec = AGENTS["A1"]
    result = ap_result(citations=[schemas.Citation(role="vendor_invoices", record_key="k")])

    reasons = escalation_reasons(spec, result, None, None)

    assert reasons
    assert any("without running the calculation" in reason for reason in reasons)


def test_an_agent_with_nothing_to_score_is_not_punished_for_not_scoring():
    """B3 computes statements, which either tie or do not. There is no rubric to run,
    and demanding one would escalate every reporting task for no reason."""
    spec = AGENTS["B3"]
    assert not set(spec.tools) & runtime.SCORING_TOOLS

    result = schemas.AgentResult(
        summary="The statements tie to the ledger.", disposition="clear",
        rationale="Every check the engine performs holds.",
        citations=[schemas.Citation(role="ledger", record_key="k")],
        proposed_action="No action proposed.", memory_checks=[])

    assert escalation_reasons(spec, result, None, None) == ()


def test_work_that_cannot_be_scored_against_an_outcome_always_reaches_a_person():
    """C4 projects a period that has not happened, so there is nothing to score it
    against. Said outright rather than by a threshold no score would ever meet."""
    spec = AGENTS["C4"]
    assert spec.escalate_when.always

    result = schemas.AgentResult(
        summary="Three periods projected under the assumptions supplied.",
        disposition="clear",
        rationale="The projection follows from the assumptions given.",
        citations=[schemas.Citation(role="ledger", record_key="k")],
        proposed_action="Weigh the projection against your own view.", memory_checks=[])

    reasons = escalation_reasons(spec, result, 100, None)

    assert reasons
    assert any("cannot be scored against an outcome" in reason for reason in reasons)


def test_a_condition_the_engine_found_escalates_even_when_the_agent_omits_it():
    """An escalation rule that reads only the model's own exception list is decorative."""
    spec = AGENTS["C3"]
    assert "unexplained_residual" in spec.escalate_when.on

    result = schemas.AgentResult(
        summary="The variance is explained by the drivers listed.", disposition="clear",
        rationale="Each driver names the transactions behind it.",
        citations=[schemas.Citation(role="ledger", record_key="k")],
        proposed_action="No action proposed.", memory_checks=[])
    assert result.exceptions == []

    engine = runtime.engine_exceptions(
        {"variance:6100": {"confidence": 96, "amount_cents": 100, "unexplained_cents": 4_000}})

    assert engine == frozenset({"unexplained_residual"})
    assert any("unexplained_residual" in reason
               for reason in escalation_reasons(spec, result, 96, 100, engine))


def test_a_fully_attributed_variance_raises_no_engine_condition():
    """A check whose exception fires on a clean baseline teaches people to skim past it."""
    assert runtime.engine_exceptions(
        {"variance:6100": {"confidence": 100, "amount_cents": 100,
                           "unexplained_cents": 0}}) == frozenset()
