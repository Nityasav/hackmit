"""Proposals agents make, and the decisions only a human may take.

The coordinator that used to build proposals is gone; escalation takes its place in
phase 4. What these cover is the part that does not change with it: a proposal is stored
under rules an agent cannot talk its way past, only a person moves it out of `pending`,
and that decision becomes precedent a later run has to reckon with.

Everything here goes through `approvals.store()` and `approvals.decide()` — the real
API — rather than through whatever happened to produce a proposal that day.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import approvals, db, ingestion
from app.accounting.money import InvariantError, JournalLine, assert_balanced
from app.main import app
from tests.conftest import HEADERS, SAMPLE_FILES, commit_pack


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    with TestClient(app, headers=HEADERS) as test_client:
        yield test_client


def _snapshot_id(ws: str) -> str:
    """The current snapshot, read on its own connection.

    Never call this inside a `with db.connect()` block: `connect()` takes an immediate
    write lock, so a second one on the same thread waits on the first and the test
    deadlocks against itself for the full fifteen-second timeout.
    """
    return ingestion.coverage(ws)["snapshot"]["id"]


BALANCED = [
    {"account": "Cloud hosting", "fund": "General", "debit_cents": 120_000, "credit_cents": 0},
    {"account": "Cloud hosting", "fund": "Restricted", "debit_cents": 0, "credit_cents": 120_000},
]


def _proposal(**overrides) -> dict:
    base = {
        "id": "ADJ-1", "agent": "A1", "kind": "decision",
        "title": "Decide how to resolve: duplicate invoice candidate",
        "summary": "Two records share a vendor, number and amount.",
        "finding_id": "finding-1", "task_id": "A1-task", "run_id": "thread-1",
        "verified": True,
    }
    return {**base, **overrides}


def _store(ws: str, **overrides) -> dict:
    proposal = _proposal(**overrides)
    with db.connect() as connection:
        approvals.store(connection, ws, proposal)
    return proposal


# --------------------------------------------------------------------------- #
# Storing a proposal
# --------------------------------------------------------------------------- #

def test_a_stored_proposal_waits_on_a_person(client):
    ws = commit_pack(client)
    snapshot = _snapshot_id(ws)
    _store(ws, snapshot_id=snapshot)

    with db.connect() as connection:
        listing = approvals.listing(connection, ws, snapshot)

    assert len(listing) == 1
    assert listing[0]["status"] == "pending"


def test_an_unbalanced_journal_is_refused_before_anyone_sees_it():
    with pytest.raises(InvariantError):
        assert_balanced([JournalLine(account="Cloud hosting", fund="General", debit_cents=100)])


def test_a_proposal_carrying_an_unbalanced_journal_is_rejected(client):
    ws = commit_pack(client)
    crooked = [dict(BALANCED[0]), {**BALANCED[1], "credit_cents": 119_000}]

    with pytest.raises(HTTPException) as caught:
        _store(ws, kind="journal", journal=crooked)

    assert caught.value.detail["code"] == "unbalanced_journal"


def test_an_unreviewed_proposal_may_never_carry_a_journal(client):
    """A journal moves money. Only a claim that survived review may propose one."""
    ws = commit_pack(client)

    with pytest.raises(HTTPException) as caught:
        _store(ws, kind="journal", journal=BALANCED, verified=False)

    assert caught.value.detail["code"] == "unreviewed_journal"


def test_a_pending_proposal_against_a_superseded_snapshot_says_so(client):
    ws = commit_pack(client)
    _store(ws, snapshot_id=_snapshot_id(ws))

    # A later import supersedes the evidence the proposal was raised against.
    later = next(f for f in SAMPLE_FILES if f.get("later"))
    batch = ingestion.stage(ws, [(later["name"], later["content"].encode(),
                                  ingestion.FileOptions(role=later["role"]))])
    ingestion.commit(ws, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key="later"))

    current = _snapshot_id(ws)
    with db.connect() as connection:
        listing = approvals.listing(connection, ws, current)

    assert listing[0]["title"].startswith("Superseded evidence")
    assert "rerun the investigation" in listing[0]["summary"].lower()


# --------------------------------------------------------------------------- #
# The human decision
# --------------------------------------------------------------------------- #

def test_a_decision_is_recorded_with_who_took_it(client):
    ws = commit_pack(client)
    _store(ws, snapshot_id=_snapshot_id(ws))

    response = client.post("/api/approvals/ADJ-1/decision",
                           json={"workspace": ws, "decision": "approved"})
    assert response.status_code == 200

    with db.connect() as connection:
        row = connection.execute(
            "SELECT status, decided_by, decided_at FROM approvals WHERE ws=? AND id=?",
            (ws, "ADJ-1")).fetchone()
    assert row["status"] == "approved"
    assert row["decided_by"] == "local-reviewer"
    assert row["decided_at"]


def test_a_decision_cannot_be_taken_twice(client):
    ws = commit_pack(client)
    _store(ws, snapshot_id=_snapshot_id(ws))
    client.post("/api/approvals/ADJ-1/decision", json={"workspace": ws, "decision": "approved"})

    with pytest.raises(HTTPException) as caught:
        approvals.decide(ws, "ADJ-1", "rejected")

    assert caught.value.detail["code"] == "already_decided"


def test_deciding_requires_the_local_reviewer(client, tmp_path, monkeypatch):
    """The reviewer marker separates an intentional local operation from any other."""
    ws = commit_pack(client)
    _store(ws, snapshot_id=_snapshot_id(ws))

    with TestClient(app) as anonymous:  # no reviewer header
        response = anonymous.post("/api/approvals/ADJ-1/decision",
                                  json={"workspace": ws, "decision": "approved"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "reviewer_required"


def test_only_approved_or_rejected_is_a_decision(client):
    ws = commit_pack(client)
    _store(ws, snapshot_id=_snapshot_id(ws))

    with pytest.raises(HTTPException) as caught:
        approvals.decide(ws, "ADJ-1", "maybe")

    assert caught.value.detail["code"] == "invalid_decision"


def test_deciding_something_that_does_not_exist_is_refused(client):
    ws = commit_pack(client)
    with pytest.raises(HTTPException) as caught:
        approvals.decide(ws, "ADJ-nope", "approved")

    assert caught.value.detail["code"] == "approval_not_found"


# --------------------------------------------------------------------------- #
# A decision becomes precedent
# --------------------------------------------------------------------------- #

def test_a_human_decision_creates_precedent_a_later_run_is_offered(client):
    ws = commit_pack(client)
    _store(ws, snapshot_id=_snapshot_id(ws))
    approvals.decide(ws, "ADJ-1", "approved")

    with db.connect() as connection:
        precedents = approvals.active_precedents(connection, ws)

    assert len(precedents) == 1
    assert precedents[0]["verdict"] == "approved"
    assert precedents[0]["decided_by"] == "local-reviewer"
    # Guidance, not a rule: it says to re-check against current evidence.
    assert "re-check" in precedents[0]["guidance"].lower()


def test_an_agent_cannot_create_precedent(client):
    """`decide()` is the only writer. Storing a proposal must not make memory."""
    ws = commit_pack(client)
    _store(ws, snapshot_id=_snapshot_id(ws))

    with db.connect() as connection:
        assert approvals.active_precedents(connection, ws) == []


def test_a_rejection_is_precedent_too(client):
    ws = commit_pack(client)
    _store(ws, snapshot_id=_snapshot_id(ws))
    approvals.decide(ws, "ADJ-1", "rejected")

    with db.connect() as connection:
        precedents = approvals.active_precedents(connection, ws)

    assert precedents[0]["verdict"] == "rejected"


def test_weighing_a_precedent_counts_as_using_it(client):
    """Applied or declined, both count: a precedent correctly declined did its job."""
    ws = commit_pack(client)
    _store(ws, snapshot_id=_snapshot_id(ws))
    approvals.decide(ws, "ADJ-1", "approved")

    with db.connect() as connection:
        precedent_id = approvals.active_precedents(connection, ws)[0]["id"]
        assert approvals.active_precedents(connection, ws)[0]["uses"] == 0
        approvals.note_precedent_uses(connection, ws, [precedent_id])

    with db.connect() as connection:
        assert approvals.active_precedents(connection, ws)[0]["uses"] == 1


def test_the_decision_reaches_the_reasoning_log_named_as_a_persons(client):
    ws = commit_pack(client)
    _store(ws, snapshot_id=_snapshot_id(ws))
    approvals.decide(ws, "ADJ-1", "approved")

    with db.connect() as connection:
        logged = approvals.decisions(connection, ws)

    assert len(logged) == 1
    assert logged[0]["actor"] == "local-reviewer"
    assert "A person, not an agent" in logged[0]["summary"]
    # It must never overstate what approving did.
    assert "No payment, posting or payroll change was executed" in logged[0]["outcome"]


# --------------------------------------------------------------------------- #
# Isolation
# --------------------------------------------------------------------------- #

def test_two_workspaces_in_one_database_both_keep_their_proposals(client):
    first, second = commit_pack(client), commit_pack(client)
    _store(first, snapshot_id=_snapshot_id(first))
    _store(second, snapshot_id=_snapshot_id(second), id="ADJ-2")

    with db.connect() as connection:
        assert [a["id"] for a in approvals.listing(connection, first)] == ["ADJ-1"]
        assert [a["id"] for a in approvals.listing(connection, second)] == ["ADJ-2"]


def test_a_decision_in_one_workspace_leaves_the_other_alone(client):
    first, second = commit_pack(client), commit_pack(client)
    _store(first, snapshot_id=_snapshot_id(first))
    _store(second, snapshot_id=_snapshot_id(second), id="ADJ-2")
    approvals.decide(first, "ADJ-1", "approved")

    with db.connect() as connection:
        assert approvals.listing(connection, second)[0]["status"] == "pending"
        assert approvals.active_precedents(connection, second) == []


def test_a_proposal_from_a_retired_agent_does_not_break_the_whole_bundle(client):
    """`AgentId` is a closed vocabulary four files agree on, and it changed when
    the agents were reworked. Rows written by the previous roster survived in
    the database naming agents the contract no longer contains, so the bundle
    failed validation and every screen in the workspace reported the service
    unreachable — over history nobody was looking at.

    The repair is to coerce the historical id here, not to widen the contract
    to keep retired names alive.
    """
    ws = commit_pack(client)
    with db.connect() as connection:
        approvals.store(connection, ws, {
            "id": "ACK-from-a-retired-agent", "agent": "ap", "kind": "decision",
            "title": "Decide how to resolve: an invoice without a receipt",
            "summary": "Raised before the agents were reworked.", "verified": False})

    response = client.get(f"/api/workspaces/{ws}/bundle")
    assert response.status_code == 200, response.text

    row = next(a for a in response.json()["approvals"] if a["id"] == "ACK-from-a-retired-agent")
    # Coerced so the contract holds, but the real author is still stated rather
    # than silently reattributed to an agent that never raised it.
    assert row["agent"] == "orchestrator"
    assert "ap" in row["title"] and "retired" in row["title"]
