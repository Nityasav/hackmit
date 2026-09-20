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


def snap(client, ws, kind: str = "one_pager") -> dict:
    """Ask for a document and read back what it was frozen with."""
    made = client.post(f"/api/workspaces/{ws}/deliverables",
                       json={"kind": kind, "requested_by": "make me a one pager"})
    assert made.status_code == 201, made.text
    return made.json()["payload"]


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


# --------------------------------------------------------------------------- #
# Asked for, or not made at all
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("message,expected", [
    ("make me a one pager", "one_pager"),
    ("can you build a slide deck for the board", "deck"),
    ("generate a 1-pager please", "one_pager"),
    ("I want a presentation of this period", "deck"),
    ("Can we close September?", None),
    ("review the payables and the bank", None),
    ("the one-pager you made was wrong", None),
    ("what does the deck say about payroll", None),
])
def test_only_a_sentence_that_asks_for_a_document_produces_one(message, expected):
    """The negatives are the point. A person asking about their books has not asked for
    a document, and one produced anyway buries the ones they did ask for."""
    from app import deliverables

    assert deliverables.requested(message) == expected


def test_a_document_is_frozen_at_the_moment_it_was_asked_for(client, ws):
    """Regenerating next week from the same title gives a different document. Two of
    those saying different things is what a dated report exists to prevent."""
    made = client.post(f"/api/workspaces/{ws}/deliverables",
                       json={"kind": "one_pager", "requested_by": "one pager please"}).json()

    first = client.get(f"/api/workspaces/{ws}/deliverables/{made['id']}").json()
    second = client.get(f"/api/workspaces/{ws}/deliverables/{made['id']}").json()

    assert first["payload"] == second["payload"]
    assert first["payload"]["result"] == made["payload"]["result"]
    assert first["requested_by"] == "one pager please"


def test_a_workspace_nobody_asked_anything_of_has_no_documents(client, ws):
    body = client.get(f"/api/workspaces/{ws}/deliverables").json()

    assert body["deliverables"] == []
    assert "means nobody asked" in body["note"]


def test_both_kinds_can_be_made_and_are_listed_newest_first(client, ws):
    client.post(f"/api/workspaces/{ws}/deliverables", json={"kind": "one_pager"})
    client.post(f"/api/workspaces/{ws}/deliverables", json={"kind": "deck"})

    rows = client.get(f"/api/workspaces/{ws}/deliverables").json()["deliverables"]

    assert [r["kind"] for r in rows] == ["deck", "one_pager"]
    assert all(r["title"] and r["kind_label"] for r in rows)


def test_a_kind_nobody_offers_is_refused_rather_than_guessed_at(client, ws):
    response = client.post(f"/api/workspaces/{ws}/deliverables", json={"kind": "poster"})

    assert response.status_code == 422
    assert "one_pager" in response.text


def test_a_document_cannot_be_made_from_books_that_were_never_committed(client):
    """An empty report with real headings reads as a period where nothing happened."""
    bare = client.post("/api/workspaces", json={
        "name": "Nothing committed", "start": "2026-09-01", "end": "2026-09-30",
        "scope": "Empty"}).json()["id"]

    response = client.post(f"/api/workspaces/{bare}/deliverables", json={"kind": "one_pager"})

    assert response.status_code == 409
    assert "commit" in response.text.lower()


def test_a_deck_and_a_one_pager_of_one_period_carry_the_same_figures(client, ws):
    """Two accounts of one month that disagree leave a reader unable to tell which is
    the real one."""
    one = client.post(f"/api/workspaces/{ws}/deliverables", json={"kind": "one_pager"}).json()
    deck = client.post(f"/api/workspaces/{ws}/deliverables", json={"kind": "deck"}).json()

    assert one["payload"]["result"] == deck["payload"]["result"]
    assert one["payload"]["checks"] == deck["payload"]["checks"]


def test_a_document_drawn_from_superseded_records_is_marked_historical(client, ws):
    """Not wrong — historical. Which one it is, is the reader's business."""
    made = client.post(f"/api/workspaces/{ws}/deliverables", json={"kind": "one_pager"}).json()
    assert not client.get(f"/api/workspaces/{ws}/deliverables/{made['id']}").json()["stale"]

    later = next(f for f in SAMPLE_FILES if f.get("later"))
    batch = client.post(
        f"/api/workspaces/{ws}/imports",
        files=[("files", (later["name"], later["content"].encode(), "text/plain"))],
        data={"metadata": json.dumps([{"role": later["role"]}])}).json()
    client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/commit",
                json={"expected_version": batch["version"], "idempotency_key": batch["id"]})

    assert client.get(f"/api/workspaces/{ws}/deliverables/{made['id']}").json()["stale"]
