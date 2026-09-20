import json
from types import SimpleNamespace

import pytest

from app import db
from app.agents import cfo
from app.agents.auditor import AuditorTools, AuditResult, Review
from .test_cfo_agent import client, committed_workspace, FakeResponses, function_call
from .test_grants_agent import provider, change_payload


def prepare(client, monkeypatch):
    ws, snapshot = committed_workspace(client)
    provider(monkeypatch, FakeResponses())
    response = client.post(f"/api/workspaces/{ws}/agent-runs", json={"snapshot_id": snapshot, "request_id": "prepare"})
    assert response.status_code == 201
    return ws, snapshot, response.json()


def review_result(fid, citation, verdict="accept"):
    return AuditResult(executive_briefing="Reviewed one limited preparer observation.", scope_assessed="Pinned evidence.",
                       limitations=["Not an audit opinion."], findings=[], evidence_requests=[], next_tasks=[],
                       reviews=[Review(finding_id=fid, verdict=verdict, rationale="The source supports the stated documentation requirement.",
                                       citations=[cfo.Citation.model_validate(citation)], required_action="Review service evidence before any adjustment.")])


class AuditResponses:
    def __init__(self):
        self.step = 0

    def create(self, **kwargs):
        assert "Internal Auditor agent" in kwargs["instructions"]
        names = {t["name"] for t in kwargs["tools"]}
        assert "submit_auditor_review" in names and "submit_grants_analysis" not in names
        if self.step == 0:
            call = function_call("get_workspace_context", {}, "context")
        elif self.step == 1:
            call = function_call("get_review_candidates", {"offset": 0}, "candidates")
        elif self.step == 2:
            self.candidate = json.loads(kwargs["input"][-1]["output"])["result"]["candidates"][0]
            self.cite = self.candidate["finding"]["citations"][0]
            call = function_call("read_source_span", {"source_id": self.cite["source_id"], "start_line": self.cite["line"], "end_line": self.cite["line"]}, "read")
        else:
            call = function_call("submit_auditor_review", review_result(self.candidate["finding_id"], self.cite).model_dump(), "submit")
        self.step += 1
        return SimpleNamespace(output=[call], usage=SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15))


def test_auditor_live_route_persistence_and_exact_review_projection(client, monkeypatch):
    ws, snapshot, preparer = prepare(client, monkeypatch)
    provider(monkeypatch, AuditResponses())
    monkeypatch.setenv("AUDITOR_MODEL", "test-auditor")
    body = {"agent": "internal_auditor", "snapshot_id": snapshot, "request_id": "audit"}
    response = client.post(f"/api/workspaces/{ws}/agent-runs", json=body)
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["model"] == "test-auditor" and run["review_targets_current"] is True
    assert run["result"]["review_scope"]["reviewed_count"] == 1
    assert run["result"]["analysis"]["reviews"][0]["finding_id"] == preparer["id"] + "-finding-1"
    assert all(t["agent"] == "internal_auditor" for t in run["result"]["tool_calls"])
    assert client.post(f"/api/workspaces/{ws}/agent-runs", json=body).json()["id"] == run["id"]
    bundle = client.get(f"/api/workspaces/{ws}/bundle").json()
    assert {a["id"] for a in bundle["agents"]} == {"cfo", "au"}
    assert "Internal Auditor: accept" in bundle["findings"][0]["summary"]
    assert bundle["findings"][0]["verified_by"] is None
    # A same-snapshot preparer rerun has new findings, never inherits prior verdicts.
    provider(monkeypatch, FakeResponses())
    client.post(f"/api/workspaces/{ws}/agent-runs", json={"snapshot_id": snapshot, "request_id": "prepare-again"})
    saved = next(r for r in client.get(f"/api/workspaces/{ws}/agent-runs").json() if r["id"] == run["id"])
    assert saved["review_targets_current"] is False
    assert "Internal Auditor: accept" not in client.get(f"/api/workspaces/{ws}/bundle").json()["findings"][0]["summary"]


def test_auditor_needs_preparer_on_current_snapshot(client, monkeypatch):
    ws, snapshot = committed_workspace(client)
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    response = client.post(f"/api/workspaces/{ws}/agent-runs", json={"agent": "internal_auditor", "snapshot_id": snapshot, "request_id": "empty"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "review_candidates_required"


def test_auditor_cannot_rubber_stamp_previews_or_copy_quotes(client, monkeypatch):
    ws, _, _ = prepare(client, monkeypatch)
    tools = AuditorTools(ws)
    tools.context()
    candidate = tools.dispatch("get_review_candidates", {"offset": 0})["candidates"][0]
    cite = candidate["finding"]["citations"][0]
    result = review_result(candidate["finding_id"], cite)
    assert any("fresh" in e for e in tools.validate_result(result))
    tools.dispatch("read_source_span", {"source_id": cite["source_id"], "start_line": cite["line"], "end_line": cite["line"]})
    assert not tools.validate_result(result)
    result.reviews[0].citations[0].quote = "Invented source quote"
    assert any("quoted text" in e for e in tools.validate_result(result))


def test_auditor_reperformance_gate_and_original_integrity(client, monkeypatch):
    ws, _, preparer = prepare(client, monkeypatch)
    ledger = cfo.SnapshotTools(ws).read_source_span(cfo.SnapshotTools(ws).list_sources("ledger")[0]["source_id"], 2, 2)
    cite = {"source_id": ledger["source_id"], "line": 2, "quote": ledger["lines"][0]["text"]}
    with db.connect() as connection:
        output = preparer["result"]
        output["analysis"]["findings"][0]["citations"] = [cite]
        connection.execute("UPDATE agent_runs SET output=? WHERE id=?", (db.encode(output), preparer["id"]))
    tools = AuditorTools(ws)
    tools.context()
    candidate = tools.dispatch("get_review_candidates", {"offset": 0})["candidates"][0]
    result = review_result(candidate["finding_id"], cite)
    tools.dispatch("read_source_span", {"source_id": cite["source_id"], "start_line": 2, "end_line": 2})
    assert any("calculations" in e for e in tools.validate_result(result))
    total = tools.dispatch("compute_ledger_totals", {})
    assert total["debit_cents"] == 1_000_000
    assert not tools.validate_result(result)
    # Fresh auditor must notice tampered normalized input, not accept repeated bad totals.
    change_payload(ws, "ledger", {"debit_cents": 123})
    fresh = AuditorTools(ws)
    assert fresh.dispatch("compute_ledger_totals", {})["reperformance"] == "blocked"
    assert not fresh.reperformed


@pytest.mark.parametrize("verdict", ["accept", "reject", "needs_evidence"])
def test_auditor_cannot_review_unknown_or_foreign_findings(client, monkeypatch, verdict):
    ws, _, _ = prepare(client, monkeypatch)
    other, _, other_run = prepare(client, monkeypatch)
    tools = AuditorTools(ws)
    tools.context()
    tools.dispatch("get_review_candidates", {"offset": 0})
    cite = other_run["result"]["analysis"]["findings"][0]["citations"][0]
    result = review_result(other_run["id"] + "-finding-1", cite, verdict)
    assert any("target" in e for e in tools.validate_result(result))
    assert all(c["preparer"] != "internal_auditor" for c in tools.candidates.values())


def test_needs_evidence_is_allowed_without_false_acceptance(client, monkeypatch):
    ws, _, _ = prepare(client, monkeypatch)
    tools = AuditorTools(ws)
    tools.context()
    candidate = tools.dispatch("get_review_candidates", {"offset": 0})["candidates"][0]
    result = review_result(candidate["finding_id"], candidate["finding"]["citations"][0], "needs_evidence")
    result.reviews[0].citations = []
    assert not tools.validate_result(result)
    result.reviews.append(result.reviews[0])
    assert any("at most once" in e for e in tools.validate_result(result))


def test_auditor_prioritizes_unreviewed_claims_and_keeps_prior_verdicts(client, monkeypatch):
    ws, snapshot, preparer = prepare(client, monkeypatch)
    with db.connect() as connection:
        output = preparer["result"]
        output["analysis"]["findings"].append(dict(output["analysis"]["findings"][0]))
        connection.execute("UPDATE agent_runs SET output=? WHERE id=?", (db.encode(output), preparer["id"]))
    tools = AuditorTools(ws)
    first, second = list(tools.candidates)
    cite = tools.candidates[first]["finding"]["citations"][0]
    for index, fid in enumerate([first, second]):
        result = review_result(fid, cite, "needs_evidence")
        with db.connect() as connection:
            connection.execute("INSERT INTO agent_runs(id,ws,agent,snapshot_id,status,model,focus,created_at,completed_at,output) VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (f"audit-{index}", ws, "internal_auditor", snapshot, "completed", "test", "review",
                                f"2026-09-20T00:00:0{index}+00:00", db.now(), db.encode({"analysis": result.model_dump()})))
        if index == 0:
            assert next(iter(AuditorTools(ws).candidates)) == second
    bundle = client.get(f"/api/workspaces/{ws}/bundle").json()
    assert all("Internal Auditor: needs_evidence" in f["summary"] for f in bundle["findings"])
