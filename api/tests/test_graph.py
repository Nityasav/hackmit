"""The phase-3 gate: one `event_id` survives invoice to match to payment to bank to cash.

Invariant 1 says a transaction keeps one identity across every domain that touches it.
These tests follow a single purchase through matching, payment, bank reconciliation and
the cash position, and assert it is recognizably the same thing at every step — which is
the property the whole event graph exists to provide.

No provider is called. The scripted model from the phase-2 tests is reused, so what is
under test is the graph's wiring and the deterministic engine, not a model's behaviour.
"""

from __future__ import annotations

import asyncio

import pytest

from app import db, events, ingestion
from app.accounting import cash, reconcile
from app.agents.budget import Meter
from app.agents.registry import AGENTS, children
from app.graph import build_graph, run_investigation
from app.graph.state import RunState, initial
from tests.conftest import SAMPLE_FILES
from tests.test_agent_runtime import FakeModel, ap_result, invoice_key, records_of

# The purchase the sample pack describes end to end: bill INV-100, matched to PO-1 and
# GR-1, paid under ACH-5001, cleared on bank line BK-1.
EVENT = "EVT-1"


@pytest.fixture
def ws(tmp_path, monkeypatch) -> str:
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    created = ingestion.create_workspace(ingestion.WorkspaceCreate(
        name="Halden Cloud Inc.", start="2026-09-01", end="2026-09-30",
        scope="September close",
        settings={"approval_limit_cents": 500_000, "materiality_cents": 100_000}))
    workspace = created["id"]
    files = [f for f in SAMPLE_FILES if not f.get("later")]
    batch = ingestion.stage(workspace, [
        (f["name"], f["content"].encode(), ingestion.FileOptions(role=f["role"]))
        for f in files])
    assert batch["status"] == "ready_to_commit", batch["issues"]
    ingestion.commit(workspace, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key="graph"))
    return workspace


# --------------------------------------------------------------------------- #
# Event identity
# --------------------------------------------------------------------------- #

def test_committing_records_materializes_the_events_they_describe(ws):
    with db.connect() as connection:
        timeline = events.timeline(connection, ws)

    assert timeline, "committed records must produce economic events"
    by_id = {event["id"]: event for event in timeline}
    assert EVENT in by_id
    assert by_id[EVENT]["kind"] == "purchase"
    assert by_id[EVENT]["period"] == "2026-09"


def test_one_event_id_carries_the_whole_purchase(ws):
    """The gate: invoice, order, receipt, payment, bank line and journals are one thing."""
    with db.connect() as connection:
        view = events.view(connection, ws, EVENT)

    assert view is not None
    assert {"vendor_invoices", "purchase_orders", "goods_receipts",
            "payments", "bank_transactions", "ledger"} <= set(view["roles"]), view["roles"]


def test_reference_data_belongs_to_no_event(ws):
    """A chart of accounts is not something that happened."""
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT role, event_id FROM records WHERE ws=? AND active=1", (ws,)).fetchall()
    by_role = {}
    for row in rows:
        by_role.setdefault(row["role"], set()).add(row["event_id"])

    assert by_role["chart"] == {None}
    assert by_role["vendors"] == {None}
    assert None not in by_role["vendor_invoices"]


def test_materializing_again_does_not_duplicate_or_renumber(ws):
    """Re-committing must not mint a second identity for the same transaction."""
    with db.connect() as connection:
        before = {e["id"]: e["created_at"] for e in events.timeline(connection, ws)}
        events.materialize(connection, ws, "2026-09-01")
        after = {e["id"]: e["created_at"] for e in events.timeline(connection, ws)}

    assert before == after, "an event keeps its identity and its history across imports"


def test_an_event_is_dated_when_the_obligation_arose(ws):
    """Earliest, not latest: the payment weeks later is part of the same event."""
    with db.connect() as connection:
        view = events.view(connection, ws, EVENT)
    ordered = next(r for r in view["records"] if r["role"] == "purchase_orders")

    assert view["event"]["occurred_on"] == ordered["payload"]["order_date"]


# --------------------------------------------------------------------------- #
# Deterministic domain work
# --------------------------------------------------------------------------- #

def test_bank_lines_reconcile_to_the_movements_the_books_record(ws):
    result = reconcile.reconcile_bank(records_of(ws), ingestion.workspace_config(ws))

    assert result["totals"]["bank_lines"] == 2
    assert result["totals"]["matched"] == 2
    assert result["totals"]["differing"] == 0
    assert not result["unmatched_bank"] and not result["unmatched_book"]


def test_an_unreferenced_bank_line_is_reported_not_guessed_at(ws):
    """Two amounts being equal is not evidence that they are the same transaction."""
    extra = ("stray.csv",
             b"bank_id,bank_account,settlement_date,direction,amount,description\n"
             b"BK-9,Operating,2026-09-15,out,1200.00,UNKNOWN DEBIT\n",
             ingestion.FileOptions(role="bank_transactions", source_system="stray"))
    batch = ingestion.stage(ws, [extra])
    ingestion.commit(ws, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key="stray"))

    result = reconcile.reconcile_bank(records_of(ws), ingestion.workspace_config(ws))
    unmatched = result["unmatched_bank"]

    assert len(unmatched) == 1 and unmatched[0]["bank_key"] == "BK-9"
    # It matches BK-1's amount exactly, and is still not matched to it.
    assert unmatched[0]["amount_cents"] == 120_000
    assert "no reference" in unmatched[0]["reason"].lower()


def test_unmatched_sides_are_never_netted_against_each_other(ws):
    result = reconcile.reconcile_bank(records_of(ws), ingestion.workspace_config(ws))
    totals = result["totals"]

    assert "unmatched_bank_cents" in totals and "unmatched_book_cents" in totals
    assert "net" not in totals
    assert "never netted" in result["note"]


def test_the_cash_position_is_derived_from_both_sides_and_says_when_they_differ(ws):
    result = cash.position(records_of(ws), ingestion.workspace_config(ws))

    assert result["closing_per_ledger_cents"] == result["closing_per_bank_cents"]
    assert result["agrees"] is True
    assert result["difference_cents"] == 0
    # Opening 20,000.00, one 1,200.00 payment out, one 4,000.00 receipt in.
    assert result["opening_cents"] == 2_000_000
    assert result["inflow_cents"] == 400_000
    assert result["outflow_cents"] == 120_000


def test_a_ledger_that_disagrees_with_the_bank_is_reported_rather_than_reconciled(ws):
    """The disagreement is the finding; presenting one number would bury it."""
    extra = ("orphan.csv",
             b"bank_id,bank_account,settlement_date,direction,amount,description\n"
             b"BK-8,Operating,2026-09-20,out,500.00,FEE NOT IN LEDGER\n",
             ingestion.FileOptions(role="bank_transactions", source_system="orphan"))
    batch = ingestion.stage(ws, [extra])
    ingestion.commit(ws, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key="orphan"))

    result = cash.position(records_of(ws), ingestion.workspace_config(ws))

    assert result["agrees"] is False
    assert result["difference_cents"] == 50_000
    assert result["closing_per_ledger_cents"] != result["closing_per_bank_cents"]


def test_the_projection_counts_only_unsettled_obligations(ws):
    result = cash.project(records_of(ws), ingestion.workspace_config(ws))

    # INV-100 was paid under ACH-5001; INV-200 was not, so only it is still committed.
    assert result["counts"]["unsettled_bills"] == 1
    assert result["committed_outflows_cents"] == 85_000
    assert result["position_before_collections_cents"] < result["opening_cents"]


def test_expected_collections_are_shown_apart_from_committed_outflows(ws):
    """They depend on a customer paying on time; outflows do not.

    The sample pack's only customer invoice is already collected, so an uncollected one
    is added here — without it the two positions coincide and the test would pass while
    measuring nothing.
    """
    uncollected = ("open_ar.csv",
                   b"record_id,customer_id,invoice_number,invoice_date,due_date,amount\n"
                   b"CI-2,C-1,SI-301,2026-09-20,2026-09-29,7500.00\n",
                   ingestion.FileOptions(role="customer_invoices", source_system="open-ar"))
    batch = ingestion.stage(ws, [uncollected])
    ingestion.commit(ws, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key="open-ar"))

    result = cash.project(records_of(ws), ingestion.workspace_config(ws))

    assert result["counts"]["uncollected_invoices"] == 1
    assert result["expected_inflows_cents"] == 750_000
    # The number that matters is the one that assumes nobody pays on time.
    assert result["position_with_collections_cents"] - result["position_before_collections_cents"] \
        == result["expected_inflows_cents"]
    assert "depend on a customer paying on time" in result["note"]


# --------------------------------------------------------------------------- #
# The graph
# --------------------------------------------------------------------------- #

def test_the_graph_is_built_from_the_registry(ws):
    graph = build_graph()
    nodes = set(graph.get_graph().nodes)

    assert {"plan", "A", "synthesize"} <= nodes
    # Every Treasurer subagent is a node inside A, from the registry rather than by hand.
    assert {spec.id for spec in children("A")} == {"A1", "A2", "A3", "A4"}


def test_an_objective_about_cash_routes_to_the_treasurer(ws):
    model = FakeModel([([], ap_result(disposition="insufficient_evidence",
                                      summary="Not enough evidence.",
                                      rationale="The records needed were not supplied.",
                                      citations=[]))])
    final = asyncio.run(run_investigation(
        ws, "Reconcile the bank and tell me the cash position.", client=model))

    assert final["plan"] == ["A"]
    assert "Treasurer" in final["plan_rationale"]


def test_an_unwired_domain_is_reported_rather_than_silently_skipped(ws):
    """A domain nobody asked anything of must not read as a clean one."""
    model = FakeModel([([], ap_result(disposition="insufficient_evidence",
                                      summary="n/a", rationale="n/a", citations=[]))])
    final = asyncio.run(run_investigation(
        ws, "Run the month-end close and test the controls.", client=model))

    unresolved = " ".join(final["unresolved"])
    assert "Controller" in unresolved and "not wired yet" in unresolved


def test_concurrent_subagents_all_reach_the_final_state(ws):
    """The reducers are what stop the last branch overwriting the other three."""
    model = FakeModel([([], ap_result(disposition="insufficient_evidence",
                                      summary="Nothing conclusive.",
                                      rationale="The supplied records do not settle it.",
                                      citations=[]))])
    final = asyncio.run(run_investigation(ws, "Review payables and cash.", client=model))

    # Four Treasurer subagents ran; every one of them is accounted for, either as a
    # finding or as an unresolved item.
    accounted = {f["agent_id"] for f in final["findings"]} | {
        key for key in final["results"]}
    assert {"A1", "A2", "A3", "A4"} <= accounted


def test_spend_is_summed_across_branches_not_overwritten(ws):
    model = FakeModel([([], ap_result(disposition="insufficient_evidence",
                                      summary="n/a", rationale="n/a", citations=[]))])
    final = asyncio.run(run_investigation(ws, "Review payables and cash.", client=model))

    per_agent = final["spend"]["by_agent"]
    assert final["spend"]["spent_cents"] == sum(per_agent.values())
    assert final["spend"]["spent_cents"] <= final["spend"]["cap_cents"]


def test_the_run_reports_a_status_and_a_briefing_with_no_authored_figures(ws):
    model = FakeModel([([], ap_result(disposition="insufficient_evidence",
                                      summary="n/a", rationale="n/a", citations=[]))])
    final = asyncio.run(run_investigation(ws, "Review payables and cash.", client=model))

    assert final["status"] in {"completed", "needs_you", "no_findings"}
    assert final["briefing"]
    # Counts in the briefing are counted from the findings, not quoted from prose.
    assert "approved, posted or paid" in final["briefing"] or "not human approval" in final["briefing"] \
        or "No agent produced" in final["briefing"]


def test_a_run_shares_one_budget_across_every_agent_in_it(ws):
    """A per-branch meter would let four agents each spend the whole run's cap."""
    model = FakeModel([([], ap_result(disposition="insufficient_evidence",
                                      summary="n/a", rationale="n/a", citations=[]))])
    final = asyncio.run(run_investigation(
        ws, "Review payables and cash.", cap_cents=20, client=model))

    assert final["spend"]["cap_cents"] == 20
    assert final["spend"]["spent_cents"] <= 20
