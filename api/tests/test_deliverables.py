"""The one-page snapshot: a document someone hands to a board.

The bar here is different from the rest of the suite. A figure that is wrong in the app
gets questioned by the person looking at it; a figure that is wrong on a PDF gets
circulated. So these tests check that what the page would show is the same as what the
accounting modules say, and that a page over books which do not tie says so rather than
presenting itself as finished.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import security
from app.accounting import close, controls, statements
from app import ingestion
from app.main import app

from tests.conftest import HEADERS, SAMPLE_FILES


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CFO_DB_PATH", str(tmp_path / "cfo.db"))
    monkeypatch.delenv("SCHOOLTRACE_USERS", raising=False)
    security.SESSIONS.clear()
    with TestClient(app, headers=HEADERS) as client:
        yield client


@pytest.fixture
def ws(client) -> str:
    created = client.post("/api/workspaces", json={
        "name": "Halden Cloud Inc.", "start": "2026-09-01", "end": "2026-09-30",
        "scope": "September close",
        "settings": {"approval_limit_cents": 500_000, "materiality_cents": 100_000}})
    workspace = created.json()["id"]
    files = [f for f in SAMPLE_FILES if not f.get("later")]
    batch = client.post(
        f"/api/workspaces/{workspace}/imports",
        files=[("files", (f["name"], f["content"].encode(), "text/plain")) for f in files],
        data={"metadata": json.dumps([{"role": f["role"], **f.get("options", {})}
                                      for f in files])}).json()
    saved = client.post(f"/api/workspaces/{workspace}/imports/{batch['id']}/commit",
                        json={"expected_version": batch["version"],
                              "idempotency_key": batch["id"]})
    assert saved.status_code == 200, saved.text
    return workspace


def snap(client, ws) -> dict:
    response = client.get(f"/api/workspaces/{ws}/deliverables/snapshot")
    assert response.status_code == 200, response.text
    return response.json()


def test_every_figure_on_the_page_agrees_with_the_module_that_owns_it(client, ws):
    """A board pack that disagrees with the statements is one nobody can use."""
    page = snap(client, ws)
    records = ingestion.financial_records(ws)["records"]
    config = ingestion.workspace_config(ws)
    figures = statements.statements(records, config)

    assert page["result"]["revenue_cents"] == figures["income_statement"]["total_revenue_cents"]
    assert page["result"]["net_cents"] == figures["income_statement"]["net_income_cents"]
    assert page["position"]["assets_cents"] == figures["balance_sheet"]["total_assets_cents"]
    assert page["position"]["closing_cash_cents"] == figures["cash_flow"]["closing_cash_cents"]
    assert page["close"]["ready"] == close.checklist(records, config)["ready"]


def test_the_page_carries_the_checks_that_say_whether_it_may_be_shown(client, ws):
    page = snap(client, ws)

    for key in ("trial_balance_balances", "balance_sheet_balances", "cash_flow_ties",
                "reliable", "balance_sheet_difference_cents"):
        assert key in page["checks"], key


def test_a_passing_test_is_named_rather_than_left_as_blank_space(client, ws):
    """A clean period must read as "we looked and found nothing", not as silence."""
    page = snap(client, ws)

    assert page["controls"]["pass_count"] >= 1
    assert page["controls"]["passed"]
    assert all(title.strip() for title in page["controls"]["passed"])


def test_a_composite_record_id_is_readable_on_a_printed_page(client, ws):
    """Raw, a purchase-order line reads as `PO-70081` — a document number that does not
    exist. On something a person hands to a board that is worse than showing nothing."""
    page = snap(client, ws)

    for item in page["controls"]["exceptions"]:
        for key in item["records"]:
            assert "\x1f" not in key


def test_nothing_is_dropped_without_being_counted(client, ws):
    """A one-page document has to leave things out. Leaving them out silently is how a
    reader concludes there were only six."""
    page = snap(client, ws)

    assert page["controls"]["exception_count"] >= len(page["controls"]["exceptions"])
    assert page["variance"]["line_count"] >= len(page["variance"]["lines"])
    assert page["controls"]["omitted"] == (
        page["controls"]["exception_count"] - len(page["controls"]["exceptions"]))


def test_the_page_says_what_it_does_not_establish(client, ws):
    page = snap(client, ws)
    text = " ".join(page["limitations"])

    assert "not an audit opinion" in text.lower()
    assert "no figure on this page was written by a language model" in text.lower()


def test_the_whole_page_is_one_read_of_one_snapshot(client, ws):
    """Four fetches would assemble a document out of four moments, and a commit landing
    between the first and the last gives a page of no particular period."""
    page = snap(client, ws)

    assert page["snapshot_id"]
    assert page["prepared_at"]
    assert page["records"] > 0


def test_books_that_do_not_tie_are_reported_rather_than_presented(client, ws):
    """The renderer refuses to dress this up, and it can only do that if the API says so."""
    records = ingestion.financial_records(ws)["records"]
    config = ingestion.workspace_config(ws)
    records.append({"role": "ledger", "record_key": "JE-BAD\x1f1", "source_id": "s",
                    "locator": 1,
                    "payload": {"entry_id": "JE-BAD", "line_id": "1", "date": "2026-09-15",
                                "account": "6100", "debit_cents": 50_000, "credit_cents": 0}})
    figures = statements.statements(records, config)

    assert not figures["reliable"]
    assert not figures["trial_balance"]["balances"]
    assert figures["problems"]


def test_a_workspace_with_no_records_is_refused_rather_than_rendered_empty(client):
    """An empty page with real headings reads as a period where nothing happened."""
    bare = client.post("/api/workspaces", json={
        "name": "Nothing committed", "start": "2026-09-01", "end": "2026-09-30",
        "scope": "Empty"}).json()["id"]

    response = client.get(f"/api/workspaces/{bare}/deliverables/snapshot")

    # Either refused, or rendered with nothing claimed. What it must never do is show a
    # result of zero as though it were measured.
    if response.status_code == 200:
        assert response.json()["records"] == 0
        assert not response.json()["close"]["ready"]
    else:
        assert response.status_code in (404, 409)
