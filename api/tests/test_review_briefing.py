"""The briefing survives the agent rework.

`live` used to be a coordinator run object carrying `status`, `briefing`,
`unresolved` and a task list. That coordinator was deleted and `live` became a
tally off the decision trail — but two readers kept the old shape. The Briefing
page crashed with "Cannot read properties of undefined (reading 'map')", and
exporting the markdown raised KeyError, for any workspace an agent had run.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app
from tests.conftest import HEADERS, commit_pack


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    with TestClient(app, headers=HEADERS) as test_client:
        yield test_client


def _decision(ws: str, *, escalated: int = 1) -> None:
    with db.connect() as connection:
        connection.execute(
            "INSERT INTO agent_decisions (id, ws, thread_id, run_id, agent, action, summary,"
            " why, confidence, evidence, escalated, model, cost_cents, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("decision-briefing", ws, "t-1", "t-1", "A1", "Accounts Payable: exception",
             "An invoice has no goods receipt recorded against it.",
             "The receipt is absent from the supplied records.", 40, "[]",
             escalated, "test-model", 1234, db.now()))


def test_the_review_reports_the_agent_tally_in_the_current_shape(client):
    ws = commit_pack(client)
    _decision(ws)

    live = client.get(f"/api/workspaces/{ws}/review").json()["live"]

    assert live == {"decisions": 1, "escalated": 1, "spend_cents": 1234}
    # The keys the old coordinator carried are gone, and nothing may read them.
    assert not {"status", "briefing", "unresolved", "tasks"} & set(live)


def test_a_workspace_with_no_agent_run_reports_no_live_review(client):
    ws = commit_pack(client)
    assert client.get(f"/api/workspaces/{ws}/review").json()["live"] is None


def test_the_briefing_exports_for_a_workspace_an_agent_has_run(client):
    """This raised KeyError on `live['status']` — a download that simply failed
    for exactly the workspaces worth briefing on."""
    ws = commit_pack(client)
    _decision(ws)

    response = client.get(f"/api/workspaces/{ws}/review/report")

    assert response.status_code == 200, response.text
    assert "Live agent review" in response.text
    assert "1 agent conclusion(s), 1 escalated to a person." in response.text


def test_the_briefing_exports_before_any_agent_has_run(client):
    ws = commit_pack(client)
    response = client.get(f"/api/workspaces/{ws}/review/report")
    assert response.status_code == 200, response.text
