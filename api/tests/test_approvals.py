"""Agents propose, humans decide, and a decision changes what the tabs show.

Approvals were a fixture that flipped a status and recomputed nothing. These
check the two rules the module is built on: no agent can reach a decision, and
no proposal may carry an amount the engine did not produce.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app import approvals, db
from app.accounting.money import InvariantError, JournalLine, assert_balanced
from app.cfo.repository import RunRepository
from app.cfo.schemas import AcceptedClaim, Calculation, Review

from app.main import app
from tests.conftest import HEADERS, SAMPLE, commit_pack
from tests.test_projection import _claim, _run, _snapshot_id


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    with TestClient(app, headers=HEADERS) as c:
        yield c


def _substantiated(ws, snapshot):
    return _run(ws, snapshot, accepted=[AcceptedClaim(
        task_id="ap-task", role="ap", claim=_claim(),
        review=Review(verdict="accept", rationale="Reperformed against the original."))])


def test_an_accepted_claim_becomes_a_proposal_waiting_on_a_human(client):
    ws = commit_pack(client, later=True)
    RunRepository().save(_substantiated(ws, _snapshot_id(ws)))

    bundle = client.get(f"/api/workspaces/{ws}/bundle").json()
    proposal = bundle["approvals"][0]
    assert proposal["status"] == "pending", "an agent may never produce anything but a pending proposal"
    assert proposal["agent"] == "ap"
    assert proposal["verified"] is True, "the claim behind it was accepted by the auditor"
    assert "approvals" not in bundle["workspace"]["disabled_tabs"]


def test_a_decision_is_recorded_with_who_took_it(client):
    ws = commit_pack(client, later=True)
    RunRepository().save(_substantiated(ws, _snapshot_id(ws)))
    approval_id = client.get(f"/api/workspaces/{ws}/bundle").json()["approvals"][0]["id"]

    response = client.post(f"/api/approvals/{approval_id}/decision",
                           json={"workspace": ws, "decision": "approved"})
    assert response.status_code == 200
    assert response.json()["approvals"][0]["status"] == "approved"

    with db.connect() as connection:
        row = connection.execute("SELECT decided_by, decided_at FROM approvals WHERE id=?",
                                 (approval_id,)).fetchone()
        event = connection.execute(
            "SELECT payload FROM events WHERE ws=? AND kind='approval_decided'", (ws,)).fetchone()
    assert row["decided_by"] == "local-reviewer" and row["decided_at"]
    assert event, "a decision must leave an event behind it"


def test_a_decision_cannot_be_taken_twice(client):
    ws = commit_pack(client, later=True)
    RunRepository().save(_substantiated(ws, _snapshot_id(ws)))
    approval_id = client.get(f"/api/workspaces/{ws}/bundle").json()["approvals"][0]["id"]

    client.post(f"/api/approvals/{approval_id}/decision", json={"workspace": ws, "decision": "approved"})
    again = client.post(f"/api/approvals/{approval_id}/decision", json={"workspace": ws, "decision": "rejected"})
    assert again.status_code == 409


def test_deciding_requires_the_local_reviewer(client):
    """The decision endpoint writes intake data, so it sits behind the same guard."""
    ws = commit_pack(client, later=True)
    RunRepository().save(_substantiated(ws, _snapshot_id(ws)))
    approval_id = client.get(f"/api/workspaces/{ws}/bundle").json()["approvals"][0]["id"]

    response = client.post(f"/api/approvals/{approval_id}/decision",
                           json={"workspace": ws, "decision": "approved"},
                           headers={"X-SchoolTrace-Reviewer": ""})
    assert response.status_code == 403


def test_a_rerun_cannot_undecide_something_a_human_decided(client):
    ws = commit_pack(client, later=True)
    run = _substantiated(ws, _snapshot_id(ws))
    RunRepository().save(run)
    approval_id = client.get(f"/api/workspaces/{ws}/bundle").json()["approvals"][0]["id"]
    client.post(f"/api/approvals/{approval_id}/decision", json={"workspace": ws, "decision": "approved"})

    # The same run is saved again, as a poll or a rerun would.
    RunRepository().save(run)
    approvals_now = client.get(f"/api/workspaces/{ws}/bundle").json()["approvals"]
    assert len(approvals_now) == 1
    assert approvals_now[0]["status"] == "approved"


def test_approving_moves_the_task_and_changes_the_report(client):
    ws = commit_pack(client, later=True)
    RunRepository().save(_substantiated(ws, _snapshot_id(ws)))

    before = client.get(f"/api/workspaces/{ws}/bundle").json()
    approval_id = before["approvals"][0]["id"]
    task = next(t for t in before["tasks"] if t["approval_id"] == approval_id)
    assert task["column"] == "needs_you", "a task waiting on a decision belongs with the human"
    outstanding = next(r for r in before["report"]["comparisons"] if r["label"] == "Decisions outstanding")
    assert outstanding["before"] == "1" and outstanding["after"] == "1"

    after = client.post(f"/api/approvals/{approval_id}/decision",
                        json={"workspace": ws, "decision": "approved"}).json()
    assert next(t for t in after["tasks"] if t["approval_id"] == approval_id)["column"] == "done"
    outstanding = next(r for r in after["report"]["comparisons"] if r["label"] == "Decisions outstanding")
    assert outstanding["before"] == "1" and outstanding["after"] == "0"


def test_approving_clears_the_exposure_of_the_finding_it_resolves(client):
    ws = commit_pack(client, later=True)
    snapshot = _snapshot_id(ws)
    run = _run(ws, snapshot, accepted=[AcceptedClaim(
        task_id="ap-task", role="ap", claim=_claim("ap-1", calculation_id="calc-1"),
        review=Review(verdict="accept", rationale="Reperformed."),
        calculation=Calculation(id="calc-1", snapshot_id=snapshot, source_ids=["s1"], amount_cents=125_00,
                                cash_delta_cents=0, category="exposure",
                                description="Unsupported invoice total"))])
    RunRepository().save(run)

    before = client.get(f"/api/workspaces/{ws}/bundle").json()
    exposure = next(r for r in before["report"]["comparisons"] if r["label"] == "Reviewed exposure")
    assert exposure["before"] == "$125.00" and exposure["after"] == "$125.00"

    approval_id = before["approvals"][0]["id"]
    after = client.post(f"/api/approvals/{approval_id}/decision",
                        json={"workspace": ws, "decision": "approved"}).json()
    exposure = next(r for r in after["report"]["comparisons"] if r["label"] == "Reviewed exposure")
    assert exposure["before"] == "$125.00" and exposure["after"] == "$0.00"


def test_an_unbalanced_journal_is_refused_before_anyone_sees_it():
    """L01 holds at write time, not at render time."""
    with pytest.raises(InvariantError):
        assert_balanced([JournalLine(account="Salary expense", fund="A", debit_cents=100),
                         JournalLine(account="Salary expense", fund="B", credit_cents=99)])


def test_a_proposal_carrying_an_unbalanced_journal_is_rejected(client, tmp_path, monkeypatch):
    ws = commit_pack(client, later=True)
    with db.connect() as connection:
        with pytest.raises(Exception) as caught:
            approvals.store(connection, ws, {
                "id": "ADJ-bad", "agent": "py", "kind": "journal", "title": "Unbalanced",
                "summary": "Should never be stored",
                "journal": [{"account": "Salary expense", "fund": "A", "debit_cents": 100, "credit_cents": 0},
                            {"account": "Salary expense", "fund": "B", "debit_cents": 0, "credit_cents": 99}]})
    assert "unbalanced_journal" in str(caught.value.detail)


def test_no_journal_is_proposed_against_a_fund_the_records_do_not_name(client):
    """A destination fund is a decision, not a derivation.

    The sample pack records an award but never names a fund to move spend into, so
    the engine's reclassification amount becomes a request for the structured
    allocation record rather than a journal against an invented fund.
    """
    ws = commit_pack(client, later=True)
    snapshot = _snapshot_id(ws)
    RunRepository().save(_run(ws, snapshot, accepted=[AcceptedClaim(
        task_id="ap-task", role="py", claim=_claim("py-1", calculation_id="calc-1"),
        review=Review(verdict="accept", rationale="Reperformed."),
        calculation=Calculation(id="calc-1", snapshot_id=snapshot, source_ids=["s1"], amount_cents=10_000_00,
                                cash_delta_cents=0, category="reclassification",
                                description="Restricted allocation with no service record."))]))

    proposal = client.get(f"/api/workspaces/{ws}/bundle").json()["approvals"][0]
    assert proposal["kind"] == "evidence"
    assert proposal["journal"] is None
    assert "do not name a destination fund" in proposal["summary"]


def test_a_public_documents_workspace_has_nothing_to_approve(client):
    """Derived from the workspace, not hardcoded: no transactions, no decisions."""
    ws = client.post("/api/workspaces", json={"name": "Published reports", "kind": "public",
                                              "start": "2026-09-01", "end": "2026-09-30",
                                              "scope": "Published documents"}).json()["id"]
    bundle = client.get(f"/api/workspaces/{ws}/bundle").json()
    assert bundle["workspace"]["disabled_tabs"] == []
    assert bundle["approvals"] == []


def test_a_finding_says_when_its_proposal_was_decided(client):
    """Before this the Findings tab was byte-identical before and after a decision.

    `Finding.status` is a closed vocabulary with no value meaning "decided", so the
    decision rides in the summary, the way the auditor's verdict already does.
    """
    ws = commit_pack(client, later=True)
    RunRepository().save(_substantiated(ws, _snapshot_id(ws)))
    before = client.get(f"/api/workspaces/{ws}/bundle").json()
    approval_id = before["approvals"][0]["id"]
    finding_before = before["findings"][0]

    after = client.post(f"/api/approvals/{approval_id}/decision",
                        json={"workspace": ws, "decision": "rejected"}).json()
    finding = next(f for f in after["findings"] if f["id"] == finding_before["id"])
    assert finding["summary"] != finding_before["summary"]
    assert finding["summary"].startswith(f"Your decision: {approval_id} rejected.")
    # The claim itself did not change, so neither does what the auditor concluded.
    assert finding["status"] == finding_before["status"] == "substantiated"


def _supersede(client, ws):
    """Commit the later source pack, which publishes a new snapshot over the old one."""
    files = [f for f in SAMPLE["files"] if f.get("later")]
    batch = client.post(f"/api/workspaces/{ws}/imports",
                        files=[("files", (f["name"], f["content"].encode(), "text/plain")) for f in files],
                        data={"metadata": json.dumps([{"role": f["role"], **f.get("options", {})}
                                                      for f in files])}).json()
    client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/commit",
                json={"expected_version": batch["version"], "idempotency_key": batch["id"]})


def test_a_pending_proposal_against_a_superseded_snapshot_says_so(client):
    """A new snapshot drops the findings, and the proposals must not look current.

    The evidence a pending proposal describes has changed underneath it — the
    finding it names is no longer in the bundle — so it is marked rather than
    silently presented as something still worth deciding on today's records.
    """
    ws = commit_pack(client, later=False)
    RunRepository().save(_run(ws, _snapshot_id(ws), accepted=[
        AcceptedClaim(task_id="ap-task", role="ap", claim=_claim("ap-1"),
                      review=Review(verdict="accept", rationale="Reperformed.")),
        AcceptedClaim(task_id="ap-task", role="ap", claim=_claim("ap-2"),
                      review=Review(verdict="accept", rationale="Reperformed."))]))
    decided, left_open = [a["id"] for a in client.get(f"/api/workspaces/{ws}/bundle").json()["approvals"]]
    client.post(f"/api/approvals/{decided}/decision", json={"workspace": ws, "decision": "approved"})

    _supersede(client, ws)
    bundle = client.get(f"/api/workspaces/{ws}/bundle").json()
    assert bundle["findings"] == [], "the run is stale, so its findings are gone"

    approvals_now = {a["id"]: a for a in bundle["approvals"]}
    assert len(approvals_now) == 2, "a decision a person took is a permanent record, never deleted"
    assert approvals_now[left_open]["title"].startswith("Superseded evidence · ")
    assert "superseded by a newer snapshot" in approvals_now[left_open]["summary"]
    # The decided one is history and is left exactly as the person left it.
    assert approvals_now[decided]["status"] == "approved"
    assert not approvals_now[decided]["title"].startswith("Superseded")



def test_an_unreviewed_proposal_may_never_carry_a_journal(client):
    """A journal moves money between funds; triage has not earned the right to propose one."""
    ws = commit_pack(client, later=True)
    with db.connect() as connection:
        with pytest.raises(Exception) as caught:
            approvals.store(connection, ws, {
                "id": "ADJ-triage", "agent": "cfo", "kind": "journal", "title": "Reclassify",
                "summary": "Balanced, but nothing independently reviewed it", "verified": False,
                "journal": [{"account": "Salary expense", "fund": "A", "debit_cents": 100, "credit_cents": 0},
                            {"account": "Salary expense", "fund": "B", "debit_cents": 0, "credit_cents": 100}]})
    assert "unreviewed_journal" in str(caught.value.detail)



def test_two_workspaces_in_one_database_both_keep_their_proposals(client):
    """One SQLite file holds every workspace, and `approvals.id` is its primary key.

    A claim id is unique only inside its run: `ap-1` is what the first AP task calls
    its first claim, everywhere. An id built from the claim alone collided across
    runs and workspaces, and `ON CONFLICT(id) DO NOTHING` dropped the second
    proposal at write time, leaving a finding no one could act on. Every other test
    gets its own data directory, which is why this only shows with two workspaces
    sharing one.
    """
    seen = []
    for _ in range(2):
        ws = commit_pack(client, later=True)
        RunRepository().save(_substantiated(ws, _snapshot_id(ws)))
        bundle = client.get(f"/api/workspaces/{ws}/bundle").json()
        assert len(bundle["findings"]) == 1
        assert len(bundle["approvals"]) == 1, "the second workspace's proposal was silently dropped"
        seen.append((ws, bundle["approvals"][0]))

    (first_ws, first), (second_ws, second) = seen
    assert first["id"] != second["id"]
    # The proposal is named after the finding it resolves, and that carries the run.
    assert first["id"] == f"ACK-{first['finding_id']}"
    assert second["id"] == f"ACK-{second['finding_id']}"
    with db.connect() as connection:
        rows = {row["id"]: row["ws"] for row in connection.execute("SELECT id, ws FROM approvals")}
    assert rows == {first["id"]: first_ws, second["id"]: second_ws}
