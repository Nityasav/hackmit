"""The phase-7 gate: a correction changes the next period's behaviour, with a recorded check.

Both halves are tested, and the second is the one that matters. Carrying a decision
forward is easy; carrying it forward *and being able to show that it was re-examined
rather than assumed* is the part that makes it safe to do at all.

So: a person decides something in September, October sees it, October re-checks it against
its own records, and the check is on the record whether it applied or not. A precedent
that is silently dropped because it no longer fits is indistinguishable from one nobody
looked at, and these tests are what keep those two apart.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import approvals, db, ingestion, memory, security
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


def period(client, name, start, end, *, continues="", files=()):
    """One period of one company. Records are committed only where a test needs them.

    Most of what is checked here is about decisions rather than books, and the sample
    pack is dated September — committing it into an October workspace fails validation
    for reasons that have nothing to do with memory.
    """
    body = {"name": name, "start": start, "end": end, "scope": "Close",
            "settings": {"approval_limit_cents": 500_000, "materiality_cents": 100_000}}
    if continues:
        body["continues"] = continues
    response = client.post("/api/workspaces", json=body)
    assert response.status_code in (200, 201), response.text
    ws = response.json()["id"]
    if files:
        batch = client.post(
            f"/api/workspaces/{ws}/imports",
            files=[("files", (f["name"], f["content"].encode(), "text/plain")) for f in files],
            data={"metadata": json.dumps([{"role": f["role"], **f.get("options", {})}
                                          for f in files])}).json()
        saved = client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/commit",
                            json={"expected_version": batch["version"],
                                  "idempotency_key": batch["id"]})
        assert saved.status_code == 200, saved.text
    return ws


def policy_file():
    return next(f for f in SAMPLE_FILES if f["role"] == "policy")


def a_decision(ws, title, verdict="approved"):
    """A person deciding a proposal, which is the only thing that writes a precedent."""
    with db.connect() as connection:
        connection.execute(
            "INSERT INTO precedents (id, ws, pattern, verdict, guidance, scope,"
            " source_finding_id, source_approval_id, decided_by, created_at, status, uses)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,'active',0)",
            (db.uid("PB"), ws, title, verdict,
             "A human reviewer decided this. Re-check it before relying on it.",
             json.dumps({"agent": "D2", "kind": "control"}), "ctl-x", "ap-x",
             "local-reviewer", db.now()))


def finding(title, status="attention", identifier="ctl-x"):
    return {"id": identifier, "title": title, "status": status}


# --------------------------------------------------------------------------- #
# Lineage
# --------------------------------------------------------------------------- #

def test_a_period_continues_the_one_before_it(client):
    september = period(client, "Halden", "2026-09-01", "2026-09-30")
    october = period(client, "Halden", "2026-10-01", "2026-10-31", continues=september)

    with db.connect() as connection:
        assert memory.lineage(connection, october) == [october, september]
        assert memory.lineage(connection, september) == [september]


def test_a_lineage_pointing_at_nothing_is_refused_not_ignored(client):
    """Ignoring it would report "no earlier decisions" in the same words as a first
    period, and nobody could tell which they were reading."""
    response = client.post("/api/workspaces", json={
        "name": "Halden", "start": "2026-10-01", "end": "2026-10-31", "scope": "Close",
        "continues": "ws-does-not-exist"})

    assert response.status_code == 422, response.text
    assert "does not exist" in response.text


def test_a_period_cannot_continue_one_that_ends_after_it_starts(client):
    october = period(client, "Halden", "2026-10-01", "2026-10-31")

    response = client.post("/api/workspaces", json={
        "name": "Halden", "start": "2026-09-01", "end": "2026-09-30", "scope": "Close",
        "continues": october})

    assert response.status_code == 422, response.text


def test_a_decision_does_not_reach_an_unrelated_company(client):
    """Inheriting a stranger's decisions is worse than inheriting none."""
    september = period(client, "Halden", "2026-09-01", "2026-09-30")
    a_decision(september, "Possible duplicate invoice")
    unrelated = period(client, "Someone else", "2026-10-01", "2026-10-31")

    with db.connect() as connection:
        assert memory.inherited(connection, unrelated) == []


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #

def test_a_decision_made_last_period_reaches_this_one(client):
    september = period(client, "Halden", "2026-09-01", "2026-09-30")
    a_decision(september, "Possible duplicate invoice")
    october = period(client, "Halden", "2026-10-01", "2026-10-31", continues=september)

    with db.connect() as connection:
        available = memory.inherited(connection, october)

    assert [p["pattern"] for p in available] == ["Possible duplicate invoice"]
    assert available[0]["from_period"] == "2026-09"
    # Marked as somebody else's period, so a reader can see where it was decided.
    assert not available[0]["own_period"]


def test_applying_a_precedent_writes_the_check_that_was_made(client):
    september = period(client, "Halden", "2026-09-01", "2026-09-30")
    a_decision(september, "Possible duplicate invoice")
    october = period(client, "Halden", "2026-10-01", "2026-10-31", continues=september)
    findings = [finding("Possible duplicate invoice")]

    with db.connect() as connection:
        result = memory.apply_to_findings(connection, october, findings)
        recorded = memory.history(connection, october)

    assert result["applied"] == 1
    assert len(recorded) == 1
    assert recorded[0]["applies"]
    assert recorded[0]["matched"] == ["ctl-x"]
    assert findings[0]["precedent"]["from_period"] == "2026-09"


def test_declining_a_precedent_is_recorded_just_as_loudly(client):
    """A precedent silently dropped is indistinguishable from one nobody looked at."""
    september = period(client, "Halden", "2026-09-01", "2026-09-30")
    a_decision(september, "Possible duplicate invoice")
    october = period(client, "Halden", "2026-10-01", "2026-10-31", continues=september)

    with db.connect() as connection:
        result = memory.apply_to_findings(
            connection, october, [finding("Order raised and invoice approved by one person")])
        recorded = memory.history(connection, october)

    assert result["declined"] == 1
    assert len(recorded) == 1
    assert not recorded[0]["applies"]
    assert "did not arise in this period" in recorded[0]["reason"]


def test_a_precedent_never_suppresses_the_finding_it_covers(client):
    """The control still fired. Hiding it would be the check quietly narrowing itself."""
    september = period(client, "Halden", "2026-09-01", "2026-09-30")
    a_decision(september, "Possible duplicate invoice")
    october = period(client, "Halden", "2026-10-01", "2026-10-31", continues=september)
    findings = [finding("Possible duplicate invoice")]

    with db.connect() as connection:
        memory.apply_to_findings(connection, october, findings)

    assert findings[0]["status"] == "attention"
    assert "not a reason it did not" in findings[0]["precedent"]["note"]


def test_a_precedent_is_declined_when_the_evidence_behind_it_changed(client):
    """A vendor name matching is not grounds to reuse a decision whose governing
    document has since been rewritten."""
    original = policy_file()
    september = period(client, "Halden", "2026-09-01", "2026-09-30", files=[original])
    a_decision(september, "Possible duplicate invoice")

    amended = dict(original, content=original["content"] + "\n\nAmended: limits revised.\n")
    october = period(client, "Halden", "2026-10-01", "2026-10-31",
                     continues=september, files=[amended])

    findings = [finding("Possible duplicate invoice")]
    with db.connect() as connection:
        result = memory.apply_to_findings(connection, october, findings)

    assert result["declined"] == 1
    assert "precedent" not in findings[0]
    assert "has changed since" in result["checks"][0]["reason"]


def test_every_precedent_available_is_checked_not_only_the_matching_ones(client):
    september = period(client, "Halden", "2026-09-01", "2026-09-30")
    a_decision(september, "Possible duplicate invoice")
    a_decision(september, "Payment for an exactly round amount")
    a_decision(september, "Vendor recorded more than once")
    october = period(client, "Halden", "2026-10-01", "2026-10-31", continues=september)

    with db.connect() as connection:
        result = memory.apply_to_findings(
            connection, october, [finding("Possible duplicate invoice")])

    assert len(result["checks"]) == 3
    assert result["applied"] == 1 and result["declined"] == 2


def test_a_check_counts_as_a_use_whether_or_not_it_applied(client):
    """A precedent correctly declined as stale did its job."""
    september = period(client, "Halden", "2026-09-01", "2026-09-30")
    a_decision(september, "Possible duplicate invoice")
    october = period(client, "Halden", "2026-10-01", "2026-10-31", continues=september)

    with db.connect() as connection:
        memory.apply_to_findings(connection, october, [finding("Something else entirely")])
        uses = connection.execute(
            "SELECT uses FROM precedents WHERE ws=?", (september,)).fetchone()["uses"]

    assert uses == 1


def test_only_a_human_decision_writes_memory(client):
    """The constraint the whole mechanism rests on, asserted against the source."""
    import inspect

    source = inspect.getsource(approvals)
    writers = [line for line in source.splitlines()
               if "INSERT INTO precedents" in line]

    assert len(writers) == 1
    assert "_record_precedent" in source
    # And nothing outside the approvals path writes that table.
    assert "INSERT INTO precedents" not in inspect.getsource(memory)


def test_a_first_period_starts_with_nothing_rather_than_a_guess(client):
    september = period(client, "Halden", "2026-09-01", "2026-09-30")

    with db.connect() as connection:
        result = memory.apply_to_findings(
            connection, september, [finding("Possible duplicate invoice")])

    assert result["checks"] == []
    assert result["applied"] == 0
