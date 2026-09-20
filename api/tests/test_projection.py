"""The projection layer: coordinator runs must reach the dashboard bundle.

Before this layer existed the five-agent coordinator wrote to a store no tab
read, so an accepted, independently reviewed claim was invisible everywhere but
its own run page. These tests pin the mapping and the rules that keep it honest.
"""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app import projection
from app.cfo.repository import RunRepository
from app.cfo.schemas import (
    AcceptedClaim, Calculation, Claim, Event, Plan, Review, Run, RunRequest, Scope,
    Source, TaskSpec, TaskState, WorkerResult,
)
from app.integrations.cfo_intake import IntakeDataSource
from app.main import app

from tests.test_cfo_intake import HEADERS, commit_pack


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    with TestClient(app, headers=HEADERS) as c:
        yield c


def _claim(claim_id="ap-1", disposition="substantiated", evidence=("s1",), calculation_id=None):
    return Claim(id=claim_id, event_key="EVT-" + claim_id, title="Invoice lacks a receipt",
                 conclusion="The invoice has no matching goods receipt in the snapshot.",
                 disposition=disposition, evidence_ids=list(evidence), calculation_id=calculation_id,
                 proposed_action="Obtain the receipt before payment.")


def _run(workspace, snapshot_id, *, accepted=(), tasks=(), status="completed", sources=("s1",)):
    run = Run(id="CFO-test-" + snapshot_id[:6], request=RunRequest(workspace=workspace, mode="live"),
              status=status, briefing="Coordinator briefing.", model_label="test-model")
    run.scope = Scope(workspace=workspace, snapshot_id=snapshot_id, institution="Fictional school",
                      period="2026-09-01 to 2026-09-30", accounting_profile="DEMO",
                      sources=[Source(id=s, title=f"{s}.csv", locator=f"{s}.csv lines 1-9", domain="ap")
                               for s in sources])
    run.plan = Plan(rationale="Split the close by domain.", tasks=[
        TaskSpec(id="ap-task", role="ap", objective="Review AP evidence", source_ids=list(sources),
                 success_criteria="Cited observations")])
    run.tasks = list(tasks) or [TaskState(spec=run.plan.tasks[0], status="done", tool_calls=3,
                                          result=WorkerResult(summary="Reviewed the invoice register."))]
    run.accepted = list(accepted)
    run.events = [
        Event(actor="cfo", action="plan.accepted", detail="Split the close by domain."),
        Event(actor="ap", action="read_source.completed", detail="s1.csv lines 1-9; sha256=abc",
              task_id="ap-task", references=["s1"]),
        Event(actor="au", action="review.accept", detail="Reperformed against the original.",
              task_id="ap-task", references=["ap-1"]),
        Event(actor="cfo", action="task.finished", detail="done", task_id="ap-task"),
        Event(actor="cfo", action="report.published", detail="Report status: completed."),
    ]
    return run


def _snapshot_id(ws):
    return asyncio.run(IntakeDataSource().snapshot(ws)).snapshot_id


def test_an_accepted_claim_becomes_a_finding_the_findings_tab_can_show(client):
    ws = commit_pack(client, later=True)
    snapshot = _snapshot_id(ws)
    accepted = AcceptedClaim(task_id="ap-task", role="ap", claim=_claim(),
                             review=Review(verdict="accept", rationale="Reperformed against the original."))
    RunRepository().save(_run(ws, snapshot, accepted=[accepted]))

    bundle = client.get(f"/api/workspaces/{ws}/bundle").json()
    finding = next(f for f in bundle["findings"] if f["title"] == "Invoice lacks a receipt")
    assert finding["agent"] == "ap"
    assert finding["status"] == "substantiated"
    assert finding["verified_by"] == "au", "an accepted claim was reviewed by the auditor by construction"
    assert "Internal Auditor accepted this claim" in finding["summary"]
    # The evidence trail points at the real source, with the locator intake published.
    assert finding["evidence"][0]["label"] == "s1.csv"
    assert finding["evidence"][0]["locator"] == "s1.csv lines 1-9"


def test_the_evidence_trail_opens_onto_the_real_original(client):
    """The 'open source' control must show source text, not an empty box."""
    ws = commit_pack(client, later=True)
    snapshot = _snapshot_id(ws)
    real_source = client.get(f"/api/workspaces/{ws}/coverage").json()["sources"][0]["id"]
    RunRepository().save(_run(ws, snapshot, sources=(real_source,), accepted=[AcceptedClaim(
        task_id="ap-task", role="ap", claim=_claim(evidence=(real_source,)),
        review=Review(verdict="accept", rationale="Reperformed."))]))

    finding = next(f for f in client.get(f"/api/workspaces/{ws}/bundle").json()["findings"]
                   if f["title"] == "Invoice lacks a receipt")
    preview = finding["evidence"][0]["source_preview"]
    assert preview, "a cited source must carry an excerpt of the committed original"
    committed = client.get(f"/api/workspaces/{ws}/sources/{real_source}").json()
    assert preview.splitlines()[0] == committed["lines"][0]["text"]


def test_an_unreadable_cited_source_keeps_its_locator(client):
    """A source removed since the run must not blank the whole trail."""
    ws = commit_pack(client, later=True)
    snapshot = _snapshot_id(ws)
    RunRepository().save(_run(ws, snapshot, sources=("gone",), accepted=[AcceptedClaim(
        task_id="ap-task", role="ap", claim=_claim(evidence=("gone",)),
        review=Review(verdict="accept", rationale="Reperformed."))]))

    node = next(f for f in client.get(f"/api/workspaces/{ws}/bundle").json()["findings"]
                if f["title"] == "Invoice lacks a receipt")["evidence"][0]
    assert node["locator"] == "gone.csv lines 1-9"
    assert node["source_preview"] is None


def test_a_finding_carries_an_amount_only_when_a_calculation_produced_it(client):
    ws = commit_pack(client, later=True)
    snapshot = _snapshot_id(ws)
    priced = AcceptedClaim(
        task_id="ap-task", role="ap", claim=_claim("ap-1", calculation_id="calc-1"),
        review=Review(verdict="accept", rationale="Reperformed."),
        calculation=Calculation(id="calc-1", snapshot_id=snapshot, source_ids=["s1"], amount_cents=125_00,
                                cash_delta_cents=0, category="exposure", description="Unsupported invoice total"))
    unpriced = AcceptedClaim(task_id="ap-task", role="ap", claim=_claim("ap-2", disposition="explained"),
                             review=Review(verdict="accept", rationale="Explained by the award terms."))
    RunRepository().save(_run(ws, snapshot, accepted=[priced, unpriced]))

    findings = {f["id"].split("-")[-1]: f for f in client.get(f"/api/workspaces/{ws}/bundle").json()["findings"]}
    assert findings["1"]["amount_cents"] == 125_00
    assert findings["2"]["amount_cents"] is None, "no calculation means no amount, ever"
    assert "No deterministic calculation" in findings["2"]["amount_note"]
    # The calculation itself is part of the evidence trail, not just a number.
    assert any(node["kind"] == "calc" for node in findings["1"]["evidence"])


def test_no_model_authored_number_can_become_an_amount(client):
    """The mapping reads `calculation`, never the claim's prose."""
    ws = commit_pack(client, later=True)
    snapshot = _snapshot_id(ws)
    claim = _claim("ap-9")
    claim.conclusion = "The overpayment is exactly $9,999.99 according to my analysis."
    RunRepository().save(_run(ws, snapshot, accepted=[AcceptedClaim(
        task_id="ap-task", role="ap", claim=claim,
        review=Review(verdict="accept", rationale="Narrow conclusion only."))]))

    finding = next(f for f in client.get(f"/api/workspaces/{ws}/bundle").json()["findings"]
                   if f["title"] == "Invoice lacks a receipt")
    assert finding["amount_cents"] is None


def test_task_states_map_onto_the_contracts_board_columns(client):
    ws = commit_pack(client, later=True)
    snapshot = _snapshot_id(ws)
    specs = {status: TaskSpec(id=f"t-{status}", role="ap", objective=f"Work in {status}", source_ids=["s1"],
                              success_criteria="Cited observations")
             for status in ("done", "working", "auditor_review", "needs_evidence", "failed", "blocked")}
    tasks = [TaskState(spec=spec, status=status) for status, spec in specs.items()]
    RunRepository().save(_run(ws, snapshot, tasks=tasks))

    columns = {t["id"].rsplit("-", 1)[-1]: t["column"]
               for t in client.get(f"/api/workspaces/{ws}/bundle").json()["tasks"]}
    assert columns["done"] == "done"
    assert columns["working"] == "working"
    assert columns["auditor_review"] == "auditor_review"
    # Everything a human must unblock lands in one place rather than disappearing.
    assert columns["needs_evidence"] == columns["failed"] == columns["blocked"] == "needs_you"


def test_a_run_planned_against_a_superseded_snapshot_is_left_out(client):
    ws = commit_pack(client, later=True)
    RunRepository().save(_run(ws, "snap-that-is-no-longer-current", accepted=[AcceptedClaim(
        task_id="ap-task", role="ap", claim=_claim(),
        review=Review(verdict="accept", rationale="Reperformed."))]))

    bundle = client.get(f"/api/workspaces/{ws}/bundle").json()
    assert bundle["findings"] == []
    assert bundle["tasks"] == []


def test_the_roster_lists_agents_that_worked_not_agents_that_were_proposed(client):
    ws = commit_pack(client, later=True)
    snapshot = _snapshot_id(ws)
    RunRepository().save(_run(ws, snapshot))

    agents = {a["id"] for a in client.get(f"/api/workspaces/{ws}/bundle").json()["agents"]}
    assert agents == {"cfo", "ap", "au"}, "the CFO planned, AP worked, the auditor reviewed"


def test_decisions_record_the_choices_and_the_tools_behind_them(client):
    ws = commit_pack(client, later=True)
    snapshot = _snapshot_id(ws)
    RunRepository().save(_run(ws, snapshot))

    decisions = client.get(f"/api/workspaces/{ws}/bundle").json()["decisions"]
    by_agent = {d["agent"] for d in decisions}
    assert {"cfo", "au", "ap"} <= by_agent
    review = next(d for d in decisions if d["agent"] == "au")
    assert review["how"], "a review decision must carry the evidence reads behind it"
    assert review["how"][0]["tool"] == "read_source"


def test_the_learning_workstreams_keys_pass_through_untouched(client):
    """Owned elsewhere; this layer must not start inventing playbooks."""
    ws = commit_pack(client, later=True)
    RunRepository().save(_run(ws, _snapshot_id(ws)))

    bundle = client.get(f"/api/workspaces/{ws}/bundle").json()
    assert bundle["playbooks"] == []
    assert bundle["ablation"] is None


def test_only_the_projection_module_builds_a_bundle():
    """One builder, or the tabs drift apart again."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in root.rglob("*.py"):
        if path.name in {"projection.py", "models.py", "store.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        if "Bundle.model_validate" in text or "-> Bundle" in text:
            offenders.append(path.relative_to(root).as_posix())
    # main.py declares the response type on its route; it delegates the building.
    assert offenders == ["main.py"], offenders
    assert "projection.bundle(ws)" in (root / "main.py").read_text(encoding="utf-8")
