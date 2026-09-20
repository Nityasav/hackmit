"""The phase-5 gate: statements tie to the ledger in exact cents, and a period closes.

Run against a generated period rather than a hand-built one. A statement is a sum over
hundreds of rows, and a fixture small enough to write by hand is small enough to make any
arithmetic look right — the interesting failures only appear at scale, where a sign error
or a missed entry has somewhere to hide.

Nothing here calls a model. `statements.py` is deterministic by design and this is the
test that keeps it that way.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app import ingestion
from app.accounting import accruals, close, statements

REPO = Path(__file__).resolve().parents[2]
PERIOD = "2026-09"


@pytest.fixture(scope="module")
def pack(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("statements")
    result = subprocess.run(
        [sys.executable, str(REPO / "fixtures" / "generate_saas.py"),
         "--out", str(out), "--seed", "2026", "--periods", PERIOD],
        capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    return out / PERIOD


@pytest.fixture
def ws(tmp_path, monkeypatch, pack) -> str:
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path / "data"))
    workspace = ingestion.create_workspace(ingestion.WorkspaceCreate(
        name="Halden Cloud Inc.", start="2026-09-01", end="2026-09-30",
        scope="September close",
        settings={"approval_limit_cents": 500_000, "materiality_cents": 100_000}))["id"]
    batch = ingestion.stage(workspace, [
        (p.name, p.read_bytes(), ingestion.FileOptions(role=p.stem))
        for p in sorted(pack.glob("*.csv"))])
    assert batch["status"] == "ready_to_commit", batch["issues"][:3]
    ingestion.commit(workspace, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key="statements"))
    return workspace


def _records(ws: str) -> list[dict]:
    return ingestion.financial_records(ws)["records"]


def _config(ws: str) -> dict:
    return ingestion.workspace_config(ws)


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #

def test_the_trial_balance_balances(ws):
    """Everything else rests on this one identity."""
    trial = statements.trial_balance(_records(ws))

    assert trial["debits_cents"] == trial["credits_cents"]
    assert trial["difference_cents"] == 0
    assert trial["balances"]


def test_the_balance_sheet_balances_to_the_cent(ws):
    sheet = statements.balance_sheet(_records(ws))

    assert sheet["difference_cents"] == 0, "assets must equal liabilities plus equity"
    assert sheet["total_assets_cents"] == (
        sheet["total_liabilities_cents"] + sheet["total_equity_cents"])
    assert sheet["balances"]


def test_the_period_result_is_shown_apart_from_retained_earnings(ws):
    """Folding it in would make the sheet balance whatever the ledger said."""
    sheet = statements.balance_sheet(_records(ws))

    assert sheet["net_income_cents"] != 0
    assert sheet["total_equity_cents"] == (
        sheet["opening_equity_cents"] + sheet["net_income_cents"])


def test_cash_flow_walks_the_entries_onto_the_balance_sheet_figure(ws):
    cash = statements.cash_flow(_records(ws))

    assert cash["difference_cents"] == 0
    assert cash["closing_cash_cents"] == cash["closing_per_balance_sheet_cents"]
    assert cash["opening_cash_cents"] + cash["net_movement_cents"] == cash["closing_cash_cents"]
    assert cash["ties"]


def test_no_cash_entry_is_dropped_on_the_way_into_an_activity(ws):
    """An entry with nowhere to go is counted and named, never discarded.

    Dropping one would make the statement tie while hiding a real movement, which is
    the failure this whole module is arranged to avoid.
    """
    cash = statements.cash_flow(_records(ws))
    by_activity = (cash["operating_cents"] + cash["investing_cents"]
                   + cash["financing_cents"])

    assert by_activity == cash["net_movement_cents"]
    assert cash["uncategorized_entries"] == []


def test_the_statements_report_themselves_as_reliable(ws):
    figures = statements.statements(_records(ws), _config(ws))

    assert figures["problems"] == []
    assert figures["reliable"]


def test_income_is_the_period_not_the_year_to_date(ws):
    """Revenue and expense accounts accumulate; using closing balances would label a
    year-to-date figure with a month's name."""
    records = _records(ws)
    income = statements.income_statement(records)
    rows = statements.balances(records)["accounts"]

    revenue_rows = [r for r in rows.values() if r["type"] == "revenue"]
    assert revenue_rows, "the fixture must have revenue for this to measure anything"
    assert income["total_revenue_cents"] == -sum(r["movement_cents"] for r in revenue_rows)


def test_a_figure_can_be_traced_back_to_the_accounts_behind_it(ws):
    """Every statement line is a sum of account balances a person can open."""
    income = statements.income_statement(_records(ws))

    assert income["total_expense_cents"] == sum(
        line["amount_cents"] for line in income["expenses"])
    assert sum(income["expense_by_category_cents"].values()) == income["total_expense_cents"]
    for line in income["expenses"]:
        assert line["account"] and line["name"]


# --------------------------------------------------------------------------- #
# What happens when the books are wrong
# --------------------------------------------------------------------------- #

def test_an_unbalanced_ledger_is_reported_rather_than_plugged(ws):
    """A balance sheet that balances because something was forced in is worse than one
    that visibly does not."""
    records = _records(ws)
    # A stray one-sided entry, the way a broken export would arrive.
    records.append({"role": "ledger", "record_key": "JE-BAD\x1f1", "source_id": "s", "locator": 1,
                    "payload": {"entry_id": "JE-BAD", "line_id": "1", "date": "2026-09-15",
                                "account": "6100", "debit_cents": 50_000, "credit_cents": 0}})

    figures = statements.statements(records, _config(ws))

    assert not figures["trial_balance"]["balances"]
    assert not figures["reliable"]
    assert any("trial balance" in p.lower() for p in figures["problems"])
    # And the difference is stated exactly, not absorbed.
    assert figures["trial_balance"]["difference_cents"] == 50_000


def test_an_account_outside_the_chart_is_named(ws):
    records = _records(ws)
    records.append({"role": "ledger", "record_key": "JE-X\x1f1", "source_id": "s", "locator": 1,
                    "payload": {"entry_id": "JE-X", "line_id": "1", "date": "2026-09-15",
                                "account": "9999", "debit_cents": 100, "credit_cents": 0}})

    figures = statements.statements(records, _config(ws))

    assert "9999" in statements.balances(records)["unknown_accounts"]
    assert any("not in the chart" in p for p in figures["problems"])


# --------------------------------------------------------------------------- #
# The close
# --------------------------------------------------------------------------- #

def test_a_clean_period_is_ready_to_close(ws):
    result = close.checklist(_records(ws), _config(ws))

    assert result["ready"], result["blocked_by"]
    assert result["counts"]["blocked"] == 0


def test_the_checklist_separates_wrong_books_from_ordinary_incompleteness(ws):
    """Unpaid bills at month end are normal; a close that waited for them would never
    happen. An unbalanced ledger is not normal."""
    result = close.checklist(_records(ws), _config(ws))
    by_id = {item["id"]: item for item in result["items"]}

    assert by_id["close-trial-balance"]["blocking"]
    assert by_id["close-balance-sheet"]["blocking"]
    assert not by_id["close-open-payables"]["blocking"]
    assert not by_id["close-control-exceptions"]["blocking"]


def test_an_unbalanced_ledger_blocks_the_close(ws):
    records = _records(ws)
    records.append({"role": "ledger", "record_key": "JE-BAD\x1f1", "source_id": "s", "locator": 1,
                    "payload": {"entry_id": "JE-BAD", "line_id": "1", "date": "2026-09-15",
                                "account": "6100", "debit_cents": 50_000, "credit_cents": 0}})

    result = close.checklist(records, _config(ws))

    assert not result["ready"]
    assert "close-trial-balance" in result["blocked_by"]


def test_a_workspace_with_no_ledger_says_so_instead_of_assessing_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    result = close.checklist([], {"start": "2026-09-01"})

    assert not result["ready"]
    assert "close-input-ledger" in result["blocked_by"]
    assert "No ledger" in result["note"]


# --------------------------------------------------------------------------- #
# Accruals
# --------------------------------------------------------------------------- #

def test_every_proposed_accrual_balances(ws):
    result = accruals.unbilled_receipts(_records(ws), _config(ws))

    for proposal in result["proposals"]:
        debits = sum(line["debit_cents"] for line in proposal["journal"])
        credits = sum(line["credit_cents"] for line in proposal["journal"])
        assert debits == credits, proposal["id"]
        assert debits == proposal["amount_cents"]


def test_an_accrual_is_only_proposed_where_a_delivery_was_recorded(ws):
    """The amount comes from a receipt that exists, never from an estimate."""
    records = _records(ws)
    result = accruals.unbilled_receipts(records, _config(ws))
    receipts = {r["record_key"] for r in records if r["role"] == "goods_receipts"}

    for proposal in result["proposals"]:
        assert proposal["receipt_key"] in receipts
        assert "recorded" in proposal["basis"] or "arrived" in proposal["basis"]


def test_an_already_billed_delivery_is_not_accrued(ws):
    """Accruing it beside its invoice would double the cost."""
    records = _records(ws)
    result = accruals.unbilled_receipts(records, _config(ws))
    billed = {r["payload"].get("po_id") for r in records
              if r["role"] == "vendor_invoices" and r["payload"].get("po_id")}

    assert not {p["po_id"] for p in result["proposals"]} & billed


def test_a_cost_the_chart_cannot_categorize_is_reported_not_defaulted(ws):
    """Posting it to a default account would misstate the category quietly."""
    result = accruals.unbilled_receipts(_records(ws), _config(ws))

    for item in result["unaccountable"]:
        assert item["reason"]
    assert "not proposed at all" in result["note"]
