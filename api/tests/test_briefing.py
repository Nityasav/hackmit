"""What the briefing screen reads, checked against a workspace an agent has worked.

This file exists because of a crash the whole suite missed. The review payload had been
rewritten to describe agent decisions, and the screen still read the shape the five
school-era agents returned, so it dereferenced a field nobody sends any more. Nineteen
tests touched the review endpoint and all of them passed, because every fixture stopped
at the rules scan — the branch that broke only renders once an agent has concluded
something.

So the rule here: **a test of a screen must supply the data the screen renders**, and a
payload the browser destructures is part of the contract whether or not a type describes
it. Each test below names the field it defends, so deleting one from the API fails here
rather than in someone's browser.
"""

import pytest
from fastapi.testclient import TestClient

from app import db, security
from app.agents.registry import AGENTS
from app.main import app
from app.reviews import role_label

from tests.conftest import HEADERS, commit_pack


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CFO_DB_PATH", str(tmp_path / "cfo.db"))
    monkeypatch.delenv("SCHOOLTRACE_USERS", raising=False)
    security.SESSIONS.clear()
    with TestClient(app, headers=HEADERS) as client:
        yield client


def scanned(client) -> str:
    ws = commit_pack(client)
    assert client.post(f"/api/workspaces/{ws}/review/scans").status_code == 201
    return ws


def decide(ws, agent="A1", *, escalated=False, reviewer=None, confidence=100):
    """One row of the decision trail, written the way the runtime writes it."""
    with db.connect() as connection:
        connection.execute(
            "INSERT INTO agent_decisions (id, ws, event_id, thread_id, run_id, agent,"
            " parent_agent, action, summary, why, confidence, evidence, reviewer,"
            " review_verdict, escalated, model, cost_cents, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (db.uid("decision"), ws, None, "thread-1", "thread-1", agent, "A",
             "Reviewed vendor invoice VI-1", "The invoice matches its order and receipt.",
             "Above the approval limit, so it stops for a person.", confidence,
             db.encode([{"role": "vendor_invoices", "record_key": "VI-1",
                         "source_id": "src-1", "line": 2}]),
             reviewer, "agree" if reviewer else None, int(escalated),
             "gpt-5.6-terra", 1234, db.now()))


def review(client, ws) -> dict:
    response = client.get(f"/api/workspaces/{ws}/review")
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# Every finding can be attributed on screen
# --------------------------------------------------------------------------- #

def test_every_finding_carries_a_label_a_person_can_read(client):
    """The browser used to hold its own table of five role codes.

    When the agents were rebuilt the table went stale, and a missing key rendered an
    empty heading rather than failing — which is why the label is sent from the API and
    asserted here.
    """
    ws = scanned(client)
    decide(ws)

    for finding in review(client, ws)["findings"]:
        assert finding["role_label"].strip(), finding["id"]
        assert finding["role_label"] != finding["role"] or not finding["role"]


def test_an_agent_is_named_by_its_id_and_its_charter_name(client):
    ws = scanned(client)
    decide(ws, "A1")

    agent_findings = [f for f in review(client, ws)["findings"] if f["origin"] == "agent"]

    assert agent_findings, "the decision an agent wrote must reach the briefing"
    assert agent_findings[0]["role_label"] == f"A1 {AGENTS['A1'].name}"


def test_an_unknown_role_is_named_rather_than_left_blank(client):
    """A role the registry does not know is a bug, and it should look like one."""
    assert role_label("").strip()
    assert role_label("not-an-agent") == "not-an-agent"


# --------------------------------------------------------------------------- #
# The live strip
# --------------------------------------------------------------------------- #

READ_BY_THE_SCREEN = ("decisions", "escalated", "spend_cents", "agents", "reviewed", "note")


def test_the_live_summary_carries_every_field_the_screen_reads(client):
    """Named one by one. Removing any of them from the API fails here, not in a browser."""
    ws = scanned(client)
    decide(ws, "A1", reviewer="D2")
    decide(ws, "A2", escalated=True)

    live = review(client, ws)["live"]

    for field in READ_BY_THE_SCREEN:
        assert field in live, field
    assert live["decisions"] == 2
    assert live["escalated"] == 1
    assert live["reviewed"] == 1
    assert live["spend_cents"] == 2468
    assert len(live["agents"]) == 2


def test_no_agent_work_reports_nothing_rather_than_a_row_of_zeros(client):
    """An empty strip says "no work yet"; zeros read as a clean result."""
    assert review(client, scanned(client))["live"] is None


def test_an_escalated_conclusion_needs_attention_whatever_the_agent_called_it(client):
    ws = scanned(client)
    decide(ws, "A1", escalated=True)

    finding = next(f for f in review(client, ws)["findings"] if f["origin"] == "agent")

    assert finding["status"] == "attention"


def test_an_unreviewed_conclusion_says_so_instead_of_reading_as_verified(client):
    ws = scanned(client)
    decide(ws, "A1", reviewer=None)

    finding = next(f for f in review(client, ws)["findings"] if f["origin"] == "agent")

    assert "review pending" in finding["review"].lower()
    assert "not a verified" in finding["review"].lower()


def test_confidence_reaches_the_screen_so_it_can_be_shown_as_computed(client):
    ws = scanned(client)
    decide(ws, "A1", confidence=100)

    finding = next(f for f in review(client, ws)["findings"] if f["origin"] == "agent")

    assert finding["confidence"] == 100


# --------------------------------------------------------------------------- #
# The exported briefing
# --------------------------------------------------------------------------- #

def test_the_briefing_exports_once_an_agent_has_concluded_something(client):
    """The export read the old live shape too, so the download broke in the same way."""
    ws = scanned(client)
    decide(ws, "A1", reviewer="D2")

    response = client.get(f"/api/workspaces/{ws}/review/report")

    assert response.status_code == 200, response.text
    assert "## Agent conclusions" in response.text
    assert f"A1 {AGENTS['A1'].name}" in response.text


def test_the_briefing_exports_when_no_agent_has_run(client):
    response = client.get(f"/api/workspaces/{scanned(client)}/review/report")

    assert response.status_code == 200, response.text
    assert "Limitations" in response.text


def test_the_export_states_model_spend_rather_than_leaving_it_off(client):
    ws = scanned(client)
    decide(ws, "A1")

    assert "12.34" in client.get(f"/api/workspaces/{ws}/review/report").text
