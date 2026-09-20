"""Integration checks for the first live-agent boundary without making provider calls."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.agents import cfo
from app import db
from tests.conftest import SAMPLE_FILES


SAMPLE = {"files": SAMPLE_FILES}
HEADERS = {"X-SchoolTrace-Reviewer": "local-reviewer"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with TestClient(app, headers=HEADERS) as test_client:
        yield test_client


def committed_workspace(client):
    response = client.post("/api/workspaces", json={
        "name": "Fictional school", "start": "2026-09-01", "end": "2026-09-30", "scope": "September close",
    })
    ws = response.json()["id"]
    files = [f for f in SAMPLE["files"] if not f.get("later")]
    staged = client.post(
        f"/api/workspaces/{ws}/imports",
        files=[("files", (f["name"], f["content"].encode(), "text/plain")) for f in files],
        data={"metadata": json.dumps([{"role": f["role"]} for f in files])},
    ).json()
    committed = client.post(f"/api/workspaces/{ws}/imports/{staged['id']}/commit", json={
        "expected_version": staged["version"], "idempotency_key": staged["id"] + ":1",
    })
    assert committed.status_code == 200, committed.text
    return ws, committed.json()["snapshot_id"]


def function_call(name, arguments, call_id):
    return SimpleNamespace(type="function_call", name=name, arguments=json.dumps(arguments), call_id=call_id)


class FakeResponses:
    def __init__(self):
        self.step = 0
        self.source_id = None

    def create(self, **kwargs):
        assert kwargs["store"] is False
        assert kwargs["parallel_tool_calls"] is False
        if self.step == 0:
            output = [function_call("get_workspace_context", {}, "call-1")]
        elif self.step == 1:
            tool_result = json.loads(kwargs["input"][-1]["output"])
            self.source_id = next(source["source_id"] for source in tool_result["result"]["sources"] if source["role"] == "policy")
            output = [function_call("read_source_span", {
                "source_id": self.source_id, "start_line": 4, "end_line": 4,
            }, "call-2")]
        else:
            output = [function_call("submit_cfo_analysis", {
                "executive_briefing": "The supplied award terms require service evidence before allocation support can be assessed.",
                "scope_assessed": "September close within the committed synthetic snapshot.",
                "limitations": ["Population completeness is not verified."],
                "findings": [{
                    "title": "Service evidence needs review", "status": "needs_evidence",
                    "summary": "The award terms specify actual service records for shared staff costs.",
                    "citations": [{"source_id": self.source_id, "line": 4,
                                   "quote": "Shared staff costs require actual service records"}],
                    "limitations": ["No conclusion on allocation allowability has been reached."],
                }],
                "evidence_requests": [{"title": "September service record", "role": "service",
                                       "reason": "Test the allocation against actual service."}],
                "next_tasks": [{"specialist": "grants_compliance", "title": "Test grant allocation support",
                                "objective": "Compare payroll allocation to award terms and service evidence."}],
            }, "call-3")]
        self.step += 1
        return SimpleNamespace(output=output, usage=SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15))

    def close(self):
        pass


def test_agent_requires_committed_snapshot_and_server_key(client, monkeypatch):
    ws = client.post("/api/workspaces", json={
        "name": "No records", "start": "2026-09-01", "end": "2026-09-30", "scope": "close",
    }).json()["id"]
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    assert client.post(f"/api/workspaces/{ws}/agent-runs", json={"snapshot_id": "missing", "request_id": "test"}).status_code == 409
    ws, snapshot_id = committed_workspace(client)
    monkeypatch.delenv("OPENAI_API_KEY")
    response = client.post(f"/api/workspaces/{ws}/agent-runs", json={"snapshot_id": snapshot_id, "request_id": "test"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "api_key_missing"


def test_merged_app_keeps_coordinator_and_snapshot_triage_routes(client, tmp_path, monkeypatch):
    from app.cfo.api import CFORuntime
    from app.cfo.repository import RunRepository
    from app.cfo.schemas import Run, RunRequest

    runtime = CFORuntime(RunRepository(tmp_path / "coordinator.sqlite3"))
    monkeypatch.setattr(app.state, "cfo_runtime", runtime, raising=False)
    ws, _ = committed_workspace(client)
    # The coordinator route is mounted, and with no adapters registered it says so
    # instead of starting a run that would have nothing real behind it.
    refused = client.post("/api/cfo/runs", json={"workspace": ws})
    assert refused.status_code == 503, refused.text
    runtime.repository.save(Run(id="CFO-routing", request=RunRequest(workspace=ws)))
    assert client.get("/api/cfo/runs/CFO-routing").status_code == 200
    assert client.get(f"/api/workspaces/{ws}/agent-runs").json() == []
    assert client.get(f"/api/workspaces/{ws}/bundle").status_code == 200


def test_cfo_agent_uses_scoped_tools_verifies_citation_and_persists(client, monkeypatch):
    ws, snapshot_id = committed_workspace(client)
    fake = SimpleNamespace(responses=FakeResponses(), close=lambda: None)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setenv("OPENAI_MODEL", "test-openai-model")
    monkeypatch.setattr(cfo, "OpenAI", lambda **_: fake)

    body = {"focus": "Review grant support", "snapshot_id": snapshot_id, "request_id": "run-once"}
    response = client.post(f"/api/workspaces/{ws}/agent-runs", json=body)
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "completed"
    assert run["snapshot_id"] == snapshot_id
    assert run["model"] == "test-openai-model"
    assert run["result"]["analysis"]["findings"][0]["status"] == "needs_evidence"
    assert [item["tool"] for item in run["result"]["tool_calls"]] == [
        "get_workspace_context", "read_source_span", "submit_cfo_analysis",
    ]
    assert run["result"]["usage"]["total_tokens"] == 45
    saved = client.get(f"/api/workspaces/{ws}/agent-runs").json()
    assert saved[0]["id"] == run["id"]
    assert saved[0]["current_snapshot"] is True
    assert saved[0]["result"]["decision"]["raw_chain_of_thought_stored"] is False
    bundle = client.get(f"/api/workspaces/{ws}/bundle")
    assert bundle.status_code == 200, bundle.text
    assert bundle.json()["workspace"]["mode"] == "live"
    assert bundle.json()["findings"][0]["status"] == "needs_evidence"
    assert client.post(f"/api/workspaces/{ws}/agent-runs", json=body).json()["id"] == run["id"]
    assert fake.responses.step == 3


def test_invalid_model_citation_is_rejected(client):
    ws, _ = committed_workspace(client)
    tools = cfo.SnapshotTools(ws)
    tools.context()
    source_id = tools.list_sources("policy")[0]["source_id"]
    result = cfo.CfoResult.model_validate({
        "executive_briefing": "Review needed.", "scope_assessed": "September.", "limitations": [],
        "findings": [{"title": "Bad citation", "status": "hypothesized", "summary": "Unsupported.",
                      "citations": [{"source_id": source_id, "line": 4, "quote": "words not in the source"}],
                      "limitations": []}],
        "evidence_requests": [], "next_tasks": [],
    })
    assert "quoted text is not present" in tools.validate_result(result)[0]


def test_snapshot_reads_survive_supersession_and_totals_include_every_record(client):
    ws, snapshot = committed_workspace(client)
    tools = cfo.SnapshotTools(ws)
    initial = tools.list_records("ledger", 100)["records"]
    # Simulate a later accepted revision: pinned historical records must remain readable.
    with db.connect() as connection:
        connection.execute("UPDATE records SET active=0 WHERE ws=? AND role='ledger'", (ws,))
    assert tools.list_records("ledger", 100)["records"] == initial
    with db.connect() as connection:
        for i in range(102):
            record_id = f"extra-{i}"
            connection.execute(
                "INSERT INTO records(id,ws,role,system,record_key,version,payload,source_id,locator) VALUES(?,?,?,?,?,?,?,?,?)",
                (record_id, ws, "ledger", "test", record_id, 1,
                 db.encode({"debit_cents": 101 if i % 2 == 0 else 0, "credit_cents": 101 if i % 2 else 0}),
                 initial[0]["source_id"], 2),
            )
            tools.record_ids.add(record_id)
    totals = tools.compute_ledger_totals()
    assert totals["record_count"] == 104
    assert totals["debit_cents"] == 1_000_000 + 51 * 101
    assert totals["balanced"] is True
    page = tools.list_records("ledger", 100)
    assert page["next_offset"] == 100
    assert len(tools.list_records("ledger", 100, 100)["records"]) == 4


def test_tool_boundaries_and_blank_citations(client):
    ws, _ = committed_workspace(client)
    other, _ = committed_workspace(client)
    tools = cfo.SnapshotTools(ws)
    foreign_id = cfo.SnapshotTools(other).list_sources("policy")[0]["source_id"]
    with pytest.raises(ValueError):
        tools.read_source_span(foreign_id, 1, 1)
    with pytest.raises(cfo.SchemaError):
        tools.dispatch("list_records", {"role": "ledger", "limit": -1, "offset": 0})
    with pytest.raises(ValueError):
        tools.dispatch("execute_sql", {"query": "SELECT * FROM records"})
    sid = tools.list_sources("policy")[0]["source_id"]
    result = cfo.CfoResult(
        executive_briefing="Draft", scope_assessed="September", limitations=[], next_tasks=[], evidence_requests=[],
        findings=[cfo.CandidateFinding(title="Claim", status="hypothesized", summary="Draft", limitations=[],
                  citations=[cfo.Citation(source_id=sid, line=1, quote=" ")])],
    )
    assert tools.validate_result(result)


def test_provider_failure_is_sanitized_and_retains_usage(client, monkeypatch):
    ws, snapshot = committed_workspace(client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    fake = FakeResponses()
    original = fake.create
    def failing(**kwargs):
        if fake.step:
            raise RuntimeError("SECRET provider details and private content")
        return original(**kwargs)
    fake.create = failing
    monkeypatch.setattr(cfo, "OpenAI", lambda **_: SimpleNamespace(responses=fake, close=lambda: None))
    result = client.post(f"/api/workspaces/{ws}/agent-runs", json={"snapshot_id": snapshot, "request_id": "failure"})
    assert result.status_code == 502
    saved = client.get(f"/api/workspaces/{ws}/agent-runs").json()[0]
    assert saved["status"] == "failed"
    assert "SECRET" not in json.dumps(saved)
    assert saved["result"]["usage"]["total_tokens"] == 15
    assert saved["result"]["tool_calls"][0]["output"]["result"]


def test_stale_snapshot_and_expired_run_recovery(client, monkeypatch):
    ws, snapshot = committed_workspace(client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    assert client.post(f"/api/workspaces/{ws}/agent-runs", json={"snapshot_id": "old", "request_id": "stale"}).status_code == 409
    with db.connect() as connection:
        connection.execute(
            "INSERT INTO agent_runs(id,ws,agent,snapshot_id,status,model,focus,created_at) VALUES(?,?,?,?,?,?,?,?)",
            ("expired", ws, "cfo", snapshot, "running", "test", "review", "2000-01-01T00:00:00+00:00"),
        )
    saved = client.get(f"/api/workspaces/{ws}/agent-runs").json()[0]
    assert saved["status"] == "failed"


def test_budget_counts_calls_not_provider_turns(client, monkeypatch):
    ws, snapshot = committed_workspace(client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    calls = [function_call("get_workspace_context", {}, f"call-{i}") for i in range(13)]
    fake = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: SimpleNamespace(output=calls, usage=None)), close=lambda: None)
    monkeypatch.setattr(cfo, "OpenAI", lambda **_: fake)
    result = client.post(f"/api/workspaces/{ws}/agent-runs", json={"snapshot_id": snapshot, "request_id": "budget"})
    assert result.status_code == 502
    saved = client.get(f"/api/workspaces/{ws}/agent-runs").json()[0]
    assert len(saved["result"]["tool_calls"]) == 12
    assert "Tool-call budget" in saved["error"]


def test_source_overview_and_cents_guard(client):
    ws, _ = committed_workspace(client)
    tools = cfo.SnapshotTools(ws)
    context = tools.context()
    assert any(source["role"] == "payroll" for source in context["sources"])
    assert context["source_previews"]
    totals = tools.compute_ledger_totals()
    assert totals["debit_display"] == "10,000.00"
    result = cfo.CfoResult(executive_briefing="Ledger total: $1,000,000", scope_assessed="September",
                           limitations=[], findings=[], evidence_requests=[], next_tasks=[])
    assert any("cents versus dollars" in error for error in tools.validate_result(result))
    result.executive_briefing = "Ledger total: $10,000.00"
    assert tools.validate_result(result) == []
