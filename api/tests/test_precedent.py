"""Human review changes what the next run is told.

Before this, `decide()` flipped a status and stopped: approve the same finding
ten times and run eleven behaved exactly like run one. The dashboard's Learning
tab and every decision's `memory_checks` were hardcoded empty.

These check the loop actually closes, and — more importantly — that it closes
in the one direction that is safe. An agent may read precedent; only a human
decision can create it.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app import approvals, db
from app.cfo.repository import RunRepository
from app.cfo.schemas import AcceptedClaim, Review

from app.main import app
from tests.test_cfo_intake import HEADERS, commit_pack
from tests.test_approvals import _substantiated
from tests.test_projection import _snapshot_id


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    with TestClient(app, headers=HEADERS) as c:
        yield c


def _decide(client, ws, verdict="approved"):
    bundle = client.get(f"/api/workspaces/{ws}/bundle").json()
    approval_id = bundle["approvals"][0]["id"]
    client.post(f"/api/approvals/{approval_id}/decision", json={"workspace": ws, "decision": verdict})
    return approval_id


def _prepared(client):
    ws = commit_pack(client, later=True)
    RunRepository().save(_substantiated(ws, _snapshot_id(ws)))
    return ws


def test_submission_schema_satisfies_strict_function_calling():
    """Regression: adding memory_checks with default_factory=list made it
    optional, and OpenAI strict function-calling rejects any schema whose
    `properties` has a key missing from `required` — so every live run 400'd
    while all 336 fake-response tests still passed. Fake responses never see
    the provider's schema validation, so this asserts the rule directly."""
    from app.agents.cfo import CfoResult

    schema = CfoResult.model_json_schema()
    assert set(schema["properties"]) == set(schema.get("required", [])), (
        "every property must be required for strict function calling; "
        f"missing: {set(schema['properties']) - set(schema.get('required', []))}"
    )


def test_no_precedent_exists_before_a_human_decides(client):
    ws = _prepared(client)
    with db.connect() as connection:
        assert approvals.active_precedents(connection, ws) == []


def test_a_human_decision_becomes_reviewed_precedent(client):
    ws = _prepared(client)
    _decide(client, ws, "approved")

    with db.connect() as connection:
        precedents = approvals.active_precedents(connection, ws)

    assert len(precedents) == 1
    assert precedents[0]["verdict"] == "approved"
    assert precedents[0]["decided_by"]
    assert precedents[0]["id"].startswith("PB-")


def test_a_rejection_is_precedent_too(client):
    """A refusal is as reusable as an approval — "we looked at this and said
    no" is exactly what a later run should not have to re-ask about."""
    ws = _prepared(client)
    _decide(client, ws, "rejected")

    with db.connect() as connection:
        assert approvals.active_precedents(connection, ws)[0]["verdict"] == "rejected"


def test_precedent_reaches_the_next_run_context(client):
    """The point of the whole loop: what the human decided is in front of the
    agent the next time it runs."""
    from app.agents.cfo import SnapshotTools

    ws = _prepared(client)
    _decide(client, ws, "approved")

    context = SnapshotTools(ws).context()
    assert len(context["reviewed_precedents"]) == 1
    assert "Re-check" in context["precedent_note"]


def test_precedent_is_offered_as_conditional_guidance_not_instruction(client):
    """A precedent that says "do this again" would be a rule. The note has to
    tell the agent to re-check it, or a stale decision gets replayed because a
    name matched."""
    from app.agents.cfo import SnapshotTools

    ws = _prepared(client)
    _decide(client, ws, "approved")

    context = SnapshotTools(ws).context()
    guidance = context["reviewed_precedents"][0]["guidance"]
    assert "Re-check" in guidance or "re-check" in guidance
    assert "not enough" in context["precedent_note"]


def test_learning_tab_shows_what_was_learned(client):
    ws = _prepared(client)
    _decide(client, ws, "approved")

    bundle = client.get(f"/api/workspaces/{ws}/bundle").json()
    assert len(bundle["playbooks"]) == 1
    assert bundle["playbooks"][0]["status"] == "active"
    assert "Approved by" in bundle["playbooks"][0]["status_note"]


def test_learning_tab_is_empty_until_a_human_decides(client):
    ws = _prepared(client)
    assert client.get(f"/api/workspaces/{ws}/bundle").json()["playbooks"] == []


def test_an_agent_cannot_create_precedent_on_its_own(client):
    """The safety property. An agent that could write its own precedent would
    promote its conclusion into guidance for its next run — the feedback loop
    spec.md §7.5 forbids. decide() is the only writer, and agents cannot
    reach it."""
    ws = _prepared(client)
    RunRepository().save(_substantiated(ws, _snapshot_id(ws)))  # another agent run

    with db.connect() as connection:
        assert approvals.active_precedents(connection, ws) == []


def test_uses_counts_a_declined_precedent_too(client):
    """Declining a stale precedent is the loop working, so it counts as a use.
    Only counting applications would make a correctly-cautious run look idle."""
    ws = _prepared(client)
    _decide(client, ws, "approved")

    with db.connect() as connection:
        precedent_id = approvals.active_precedents(connection, ws)[0]["id"]
        approvals.note_precedent_uses(connection, ws, [precedent_id])
        assert approvals.active_precedents(connection, ws)[0]["uses"] == 1
