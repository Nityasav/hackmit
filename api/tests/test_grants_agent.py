"""Grant agent checks use synthetic records and mocked provider calls only."""

import json
from types import SimpleNamespace

import pytest

from app import db
from app.agents import cfo
from app.agents.grants import GrantsTools
from .test_cfo_agent import client, committed_workspace, FakeResponses, function_call


class GrantsResponses(FakeResponses):
    def create(self, **kwargs):
        assert "Grants & Compliance" in kwargs["instructions"]
        names = {t["name"] for t in kwargs["tools"]}
        assert "submit_grants_analysis" in names and "submit_cfo_analysis" not in names
        response = super().create(**kwargs)
        call = response.output[0]
        if call.name == "read_source_span":
            response.output = [function_call("check_grant", {"award_id": "GRANT-1"}, "check")]
        elif call.name == "submit_cfo_analysis":
            call.name = "submit_grants_analysis"
        return response


def provider(monkeypatch, responses):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setattr(cfo, "OpenAI", lambda **_: SimpleNamespace(responses=responses, close=lambda: None))


def change_payload(ws, role, changes):
    with db.connect() as connection:
        row = connection.execute("SELECT * FROM records WHERE ws=? AND role=? LIMIT 1", (ws, role)).fetchone()
        connection.execute("UPDATE records SET payload=? WHERE id=?", (db.encode({**json.loads(row["payload"]), **changes}), row["id"]))


def test_grants_run_persists_separately_and_keeps_cfo_findings(client, monkeypatch):
    ws, snapshot = committed_workspace(client)
    provider(monkeypatch, FakeResponses())
    body = {"snapshot_id": snapshot, "request_id": "cfo"}
    assert client.post(f"/api/workspaces/{ws}/agent-runs", json=body).status_code == 201
    assert client.post(f"/api/workspaces/{ws}/agent-runs", json={**body, "agent": "grants_compliance"}).status_code == 409
    provider(monkeypatch, GrantsResponses())
    monkeypatch.setenv("GRANTS_MODEL", "test-grants-model")
    body = {**body, "agent": "grants_compliance", "request_id": "grants"}
    response = client.post(f"/api/workspaces/{ws}/agent-runs", json=body)
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["agent"] == "grants_compliance" and run["status"] == "completed"
    assert run["model"] == "test-grants-model"
    assert all(t["agent"] == "grants_compliance" for t in run["result"]["tool_calls"])
    assert client.post(f"/api/workspaces/{ws}/agent-runs", json=body).json()["id"] == run["id"]
    bundle = client.get(f"/api/workspaces/{ws}/bundle").json()
    assert {a["id"] for a in bundle["agents"]} == {"cfo", "gr"}
    assert {f["agent"] for f in bundle["findings"]} == {"cfo", "gr"}
    assert {d["agent"] for d in bundle["decisions"]} == {"cfo", "gr"}
    assert all(f["verified_by"] is None for f in bundle["findings"])
    # New source revision makes both agents' previous runs stale, without losing history.
    with db.connect() as connection:
        manifest = connection.execute("SELECT manifest FROM snapshots WHERE id=?", (snapshot,)).fetchone()[0]
        connection.execute("UPDATE snapshots SET stale=1 WHERE ws=?", (ws,))
        connection.execute("INSERT INTO snapshots VALUES(?,?,?,?,?,0)", ("new-snapshot", ws, 2, db.now(), manifest))
    assert all(not r["current_snapshot"] for r in client.get(f"/api/workspaces/{ws}/agent-runs").json())
    assert client.get(f"/api/workspaces/{ws}/bundle").json()["findings"] == []


@pytest.mark.parametrize("start,end,state", [
    ("2026-09-01", "2026-09-30", "within"),
    ("2026-09-01", "2026-09-01", "within"),
    ("2026-08-01", "2026-08-31", "outside"),
    ("2027-07-01", "2027-07-31", "outside"),
    ("2026-08-31", "2026-09-01", "overlaps"),
])
def test_grant_service_window_uses_service_dates_not_pay_date(client, start, end, state):
    ws, _ = committed_workspace(client)
    change_payload(ws, "payroll", {"service_start": start, "service_end": end, "pay_date": "2050-01-01"})
    checked = GrantsTools(ws).check_grant("GRANT-1")
    assert checked["service_period_counts"][state] == 1
    assert checked["payroll_award_total_cents"] == 1_000_000
    assert checked["ceiling_cents"] == 5_000_000
    assert checked["recorded_payroll_exceeds_ceiling"] is False
    assert checked["service_period_checks"][0]["full_payroll_cost_charged"] is True


def test_missing_and_ambiguous_awards_do_not_get_a_clearance(client):
    ws, _ = committed_workspace(client)
    tools = GrantsTools(ws)
    assert tools.check_grant("nonexistent")["recorded_payroll_exceeds_ceiling"] is None
    change_payload(ws, "payroll", {"award_id": "unknown-award"})
    checked = tools.check_grant("unknown-award")
    assert checked["award_status"] == "missing"
    assert checked["service_period_counts"]["unknown"] == 1
    with db.connect() as connection:
        row = connection.execute("SELECT * FROM records WHERE ws=? AND role='grants'", (ws,)).fetchone()
        connection.execute("INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?)", (
            "duplicate-award", ws, "grants", "other-system", row["record_key"], 1,
            row["payload"], row["source_id"], row["locator"], 1))
    tools.record_ids.add("duplicate-award")
    checked = tools.check_grant("GRANT-1")
    assert checked["award_status"] == "ambiguous"
    assert checked["ceiling_cents"] is None


def test_grant_sum_uses_full_pinned_payroll_not_ledger_or_page(client):
    ws, _ = committed_workspace(client)
    tools = GrantsTools(ws)
    with db.connect() as connection:
        row = connection.execute("SELECT * FROM records WHERE ws=? AND role='payroll'", (ws,)).fetchone()
        for i in range(105):
            rid = f"extra-payroll-{i}"
            connection.execute("INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?)", (
                rid, ws, "payroll", "test", rid, 1, row["payload"], row["source_id"], row["locator"], 0))
            tools.record_ids.add(rid)
        connection.execute("UPDATE records SET active=0 WHERE ws=?", (ws,))
    checked = tools.check_grant("GRANT-1")
    assert checked["payroll_record_count"] == 106
    assert checked["payroll_award_total_cents"] == 106_000_000
    assert checked["recorded_payroll_exceeds_ceiling"] is True
    assert checked["service_period_counts"]["within"] == 106
    assert checked["checks_truncated"] and len(checked["service_period_checks"]) == 40


def test_grants_tools_reject_scope_escape_and_invalid_arguments(client):
    ws, _ = committed_workspace(client)
    other, _ = committed_workspace(client)
    tools = GrantsTools(ws)
    foreign = GrantsTools(other).list_sources("grants")[0]["source_id"]
    with pytest.raises(ValueError):
        tools.dispatch("read_source_span", {"source_id": foreign, "start_line": 1, "end_line": 2})
    with pytest.raises(cfo.SchemaError):
        tools.dispatch("check_grant", {"award_id": "GRANT-1", "workspace": other})
    with pytest.raises(ValueError):
        tools.dispatch("submit_cfo_analysis", {})
    assert client.post(f"/api/workspaces/{ws}/agent-runs", json={
        "agent": "arbitrary", "snapshot_id": "missing", "request_id": "bad",
    }).status_code == 422


def test_grants_requires_context_and_deterministic_check(client):
    ws, _ = committed_workspace(client)
    tools = GrantsTools(ws)
    result = cfo.CfoResult(executive_briefing="Evidence review needed.", scope_assessed="Supplied records.",
                           limitations=[], findings=[], evidence_requests=[], next_tasks=[])
    assert tools.validate_result(result)
    tools.context()
    assert any("check_grant" in e for e in tools.validate_result(result))
    tools.check_grant("not-in-this-snapshot")
    assert tools.validate_result(result)
    tools.check_grant("GRANT-1")
    assert not tools.validate_result(result)


def test_grants_failure_retains_history_without_fake_findings(client, monkeypatch):
    ws, snapshot = committed_workspace(client)
    fake = GrantsResponses()
    original = fake.create
    def failing(**kwargs):
        if fake.step:
            raise RuntimeError("private provider details")
        return original(**kwargs)
    fake.create = failing
    provider(monkeypatch, fake)
    response = client.post(f"/api/workspaces/{ws}/agent-runs", json={
        "agent": "grants_compliance", "snapshot_id": snapshot, "request_id": "failure",
    })
    assert response.status_code == 502
    saved = client.get(f"/api/workspaces/{ws}/agent-runs").json()[0]
    assert saved["agent"] == "grants_compliance" and saved["status"] == "failed"
    assert len(saved["result"]["tool_calls"]) == 1
    assert "private provider details" not in json.dumps(saved)
    assert client.get(f"/api/workspaces/{ws}/bundle").json()["findings"] == []


def test_running_cfo_blocks_grants_without_a_provider_call(client, monkeypatch):
    ws, snapshot = committed_workspace(client)
    provider(monkeypatch, GrantsResponses())
    with db.connect() as connection:
        connection.execute("INSERT INTO agent_runs(id,ws,agent,snapshot_id,status,model,focus,created_at) VALUES(?,?,?,?,?,?,?,?)",
                           ("active-cfo", ws, "cfo", snapshot, "running", "test", "review", db.now()))
    response = client.post(f"/api/workspaces/{ws}/agent-runs", json={
        "agent": "grants_compliance", "snapshot_id": snapshot, "request_id": "blocked",
    })
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "agent_already_running"
    assert len(client.get(f"/api/workspaces/{ws}/agent-runs").json()) == 1


def test_frequent_grants_runs_do_not_hide_cfo_history(client):
    ws, snapshot = committed_workspace(client)
    with db.connect() as connection:
        for i in range(23):
            connection.execute("INSERT INTO agent_runs(id,ws,agent,snapshot_id,status,model,focus,created_at) VALUES(?,?,?,?,?,?,?,?)",
                               (f"run-{i}", ws, "cfo" if i == 0 else "grants_compliance", snapshot,
                                "failed", "test", "review", f"2026-09-01T00:00:{i:02}+00:00"))
    saved = client.get(f"/api/workspaces/{ws}/agent-runs").json()
    assert len(saved) == 21
    assert sum(r["agent"] == "cfo" for r in saved) == 1
