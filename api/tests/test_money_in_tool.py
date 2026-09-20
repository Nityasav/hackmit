"""The CFO agent's deterministic money-in calculation.

Before this tool existed the agent could read collections.csv and cite COL-008's
1,500.00, but no tool could derive their 2,400.00 total, so `validate_result`
rejected every submission naming it and the run burned its whole call budget
failing. `test_agent_can_state_a_derived_money_in_total` is that scenario.
"""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.agents import cfo
from . import eval_support as support

# Amounts the pack's README records as engine output, in cents.
PLANTED = {"rc-undeposited-2b95aeb57ec7": 240000, "rc-deposit-shortfall-d432ab8cb466": 15000,
           "rc-pledge-overdue": 175000, "rc-fees-outstanding": 17000}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with TestClient(app, headers=support.HEADERS) as test_client:
        yield test_client


@pytest.fixture
def money_in(client):
    ws, snapshot, lines = support.upload_pack(client, "Money in", support.money_in_files())
    return client, ws, snapshot, lines


def test_tool_reports_the_amounts_the_director_review_reports(money_in):
    """One engine, two readers. A second implementation could drift from the scan."""
    client, ws, _, _ = money_in
    tool = cfo.SnapshotTools(ws).compute_money_in_checks()
    scan = client.post(f"/api/workspaces/{ws}/review/scans").json()
    assert {c["id"]: c["amount_cents"] for c in tool["checks"]} == \
           {f["id"]: f["amount_cents"] for f in scan["checks"] if f["id"].startswith("rc-")}
    assert {c["id"]: c["amount_cents"] for c in tool["checks"] if c["amount_cents"]} == PLANTED


def test_derived_amounts_become_stateable(money_in):
    """The point of the tool: a total no single record carries passes validation."""
    _, ws, _, _ = money_in
    tools = cfo.SnapshotTools(ws)
    assert 240000 not in tools.allowed_amounts
    tools.compute_money_in_checks()
    assert {240000, 15000} <= tools.allowed_amounts


def test_calculation_is_pinned_to_its_snapshot(money_in):
    """A later commit must not change what an in-flight run computed."""
    client, ws, _, _ = money_in
    tools = cfo.SnapshotTools(ws)
    before = tools.compute_money_in_checks()
    extra = ("record_id,collected_by,collection_date,method,amount,fee_record_id,deposit_reference,collection_reference\n"
             "COL-013,athletics,2026-09-16,cash,500.00,,DEP-REF-0009,\n")
    staged = client.post(f"/api/workspaces/{ws}/imports",
                         files=[("files", ("collections.csv", extra.encode(), "text/csv"))],
                         data={"metadata": json.dumps([{"role": "collections"}])}).json()
    committed = client.post(f"/api/workspaces/{ws}/imports/{staged['id']}/commit", json={
        "expected_version": staged["version"], "idempotency_key": f"{staged['id']}:1"})
    assert committed.status_code == 200, committed.text
    assert tools.compute_money_in_checks() == before
    # A run started after that commit does see it.
    fresh = cfo.SnapshotTools(ws).compute_money_in_checks()
    assert fresh != before


def test_other_accounting_profiles_are_refused(money_in):
    """The collections rules are USD management-profile rules; they are not universal."""
    _, ws, _, _ = money_in
    tools = cfo.SnapshotTools(ws)
    tools.workspace["currency"] = "CAD"   # the guard, without a second intake path
    with pytest.raises(ValueError):
        tools.compute_money_in_checks()


def test_the_tool_is_read_only_and_reaches_no_other_domain(money_in):
    """Money-in scope only: it must not hand back AP, payroll or grant findings."""
    _, ws, _, _ = money_in
    output = cfo.SnapshotTools(ws).compute_money_in_checks()
    assert all(check["id"].startswith("rc-") for check in output["checks"])
    assert set(output["record_counts"]) == set(cfo.MONEY_IN_ROLES)
    assert "must never be added" in output["note"]


class Fake:
    """Reads the pack, runs the calculation, then states the derived total."""

    def __init__(self, ws, use_tool=True):
        self.ws, self.use_tool, self.step = ws, use_tool, 0

    def create(self, **kwargs):
        if len(kwargs["input"]) == 1:
            self.step = 0
        self.step += 1
        sources = {s["name"]: s for s in cfo.SnapshotTools(self.ws).context()["sources"]}
        collections = sources["collections.csv"]
        if self.step == 1:
            call = ("get_workspace_context", {})
        elif self.step == 2:
            call = ("read_source_span", {"source_id": collections["source_id"], "start_line": 1,
                                         "end_line": collections["line_count"]})
        elif self.step == 3 and self.use_tool:
            call = ("compute_money_in_checks", {})
        else:
            call = ("submit_cfo_analysis", {
                "memory_checks": [], "scope_assessed": "September money-in.",
                "executive_briefing": "Receipts under DEP-REF-0009 total $2,400.00 and no supplied deposit answers them.",
                "limitations": ["Population completeness is not verified."],
                "findings": [{"title": "Undeposited athletics receipts", "status": "needs_evidence",
                              "summary": "COL-008 and COL-009 total $2,400.00 against DEP-REF-0009.",
                              "citations": [{"source_id": collections["source_id"], "line": 9,
                                             "quote": "COL-008,athletics,2026-09-14,cash,1500.00"}],
                              "limitations": []}],
                "evidence_requests": [], "next_tasks": []})
        return SimpleNamespace(
            output=[SimpleNamespace(type="function_call", name=call[0],
                                    arguments=json.dumps(call[1]), call_id=f"c{self.step}")],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15))

    def close(self):
        pass


@pytest.mark.parametrize("use_tool,expected", [(True, 201), (False, 502)])
def test_agent_can_state_a_derived_money_in_total(money_in, monkeypatch, use_tool, expected):
    """With the calculation the run completes; without it the same claim still fails closed."""
    client, ws, snapshot, _ = money_in
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setattr(cfo, "OpenAI",
                        lambda **_: SimpleNamespace(responses=Fake(ws, use_tool), close=lambda: None))
    response = client.post(f"/api/workspaces/{ws}/agent-runs", json={
        "agent": "cfo", "snapshot_id": snapshot, "request_id": "money-in",
        "focus": "Reconcile September receipts to the bank deposits."})
    assert response.status_code == expected, response.text
    saved = client.get(f"/api/workspaces/{ws}/agent-runs").json()[0]
    if use_tool:
        assert "$2,400.00" in saved["result"]["analysis"]["executive_briefing"]
        assert len(saved["result"]["tool_calls"]) == 4
    else:
        # Every submission rejected for an amount no inspected record supports.
        assert saved["status"] == "failed"
        rejected = [c for c in saved["result"]["tool_calls"] if c["tool"] == "submit_cfo_analysis"]
        assert rejected and all("unsupported by inspected records" in json.dumps(c["output"])
                                for c in rejected)
