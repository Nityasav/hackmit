"""Development safety matrix, not the independent held-out benchmark in the spec."""

import json
from types import SimpleNamespace

import pytest

from app import db
from app.agents import cfo
from app.agents.grants import GrantsTools
from app.agents.auditor import AuditorTools
from .test_cfo_agent import client, committed_workspace, FakeResponses, function_call
from .test_grants_agent import provider, GrantsResponses
from .test_auditor_agent import prepare, AuditResponses


@pytest.mark.parametrize("tool_type", [cfo.SnapshotTools, GrantsTools, AuditorTools])
@pytest.mark.parametrize("name", ["execute_sql", "approve_adjustment", "release_payment", "read_file"])
def test_every_agent_refuses_mutation_and_escape_tools(client, tool_type, name):
    ws, _ = committed_workspace(client)
    tools = tool_type(ws)
    assert name not in {t["name"] for t in tools.tool_definitions()}
    with pytest.raises(ValueError):
        tools.dispatch(name, {})


@pytest.mark.parametrize("agent,responses", [
    ("cfo", FakeResponses), ("grants_compliance", GrantsResponses), ("internal_auditor", AuditResponses),
])
@pytest.mark.parametrize("failure", ["incomplete", "no_tools", "malformed", "provider_error"])
def test_all_agents_fail_closed_and_retain_history(client, monkeypatch, agent, responses, failure):
    ws, snapshot, _ = prepare(client, monkeypatch)
    fake = responses()
    original = fake.create
    count = 0
    def create(**kwargs):
        nonlocal count
        count += 1
        if count == 1:
            return original(**kwargs)
        if failure == "provider_error":
            raise RuntimeError("PRIVATE_PROVIDER_SECRET")
        call = function_call("get_workspace_context", {}, "bad")
        call.arguments = "{malformed"
        return SimpleNamespace(status="incomplete" if failure == "incomplete" else "completed",
                               output=[] if failure == "no_tools" else [call], usage=None)
    fake.create = create
    provider(monkeypatch, fake)
    before = client.get(f"/api/workspaces/{ws}/bundle").json()["findings"]
    response = client.post(f"/api/workspaces/{ws}/agent-runs", json={
        "agent": agent, "snapshot_id": snapshot, "request_id": "failure-matrix"})
    assert response.status_code == 502
    failed = next(r for r in client.get(f"/api/workspaces/{ws}/agent-runs").json() if r["status"] == "failed")
    assert "analysis" not in failed["result"]
    assert 1 <= len(failed["result"]["tool_calls"]) <= cfo.MAX_TOOL_CALLS
    assert "PRIVATE_PROVIDER_SECRET" not in json.dumps(failed)
    assert client.get(f"/api/workspaces/{ws}/bundle").json()["findings"] == before


@pytest.mark.parametrize("agent,responses", [
    ("cfo", FakeResponses), ("grants_compliance", GrantsResponses), ("internal_auditor", AuditResponses),
])
def test_snapshot_changes_during_execution_never_publish_current_findings(client, monkeypatch, agent, responses):
    ws, snapshot, _ = prepare(client, monkeypatch)
    fake = responses()
    original = fake.create
    def create(**kwargs):
        response = original(**kwargs)
        if fake.step == 1:
            with db.connect() as connection:
                manifest = connection.execute("SELECT manifest FROM snapshots WHERE id=?", (snapshot,)).fetchone()[0]
                connection.execute("UPDATE snapshots SET stale=1 WHERE ws=?", (ws,))
                connection.execute("INSERT INTO snapshots VALUES(?,?,?,?,?,0)", ("replacement", ws, 2, db.now(), manifest))
        return response
    fake.create = create
    provider(monkeypatch, fake)
    response = client.post(f"/api/workspaces/{ws}/agent-runs", json={
        "agent": agent, "snapshot_id": snapshot, "request_id": "snapshot-race"})
    assert response.status_code == 201
    assert response.json()["current_snapshot"] is False
    assert client.get(f"/api/workspaces/{ws}/bundle").json()["findings"] == []


@pytest.mark.parametrize("amount", ["$10,000.009", "USD 10000.001", "$10000.0000000000000000000000001"])
def test_money_guard_never_rounds_an_unsupported_subcent_claim(client, amount):
    ws, _ = committed_workspace(client)
    tools = cfo.SnapshotTools(ws)
    tools.context()
    tools.compute_ledger_totals()
    result = cfo.CfoResult(memory_checks=[], executive_briefing=f"Total: {amount}", scope_assessed="Test",
                           limitations=[], findings=[], evidence_requests=[], next_tasks=[])
    assert tools.validate_result(result)
