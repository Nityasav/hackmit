"""Labelled management-check cases and the full local judge journey.

These are deterministic regression cases, not held-out LLM accuracy measurements.
"""
import json
import os
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import db, ingestion, security
from app.accounting.review import checks
from app.cfo.api import runtime
from app.cfo.schemas import AcceptedClaim, Claim, Review, Run, RunRequest, Scope
from tests.conftest import TRANSACTION_FILES, sample_files, withheld_service_record

HEADERS = {"X-SchoolTrace-Reviewer": "local-reviewer"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CFO_DB_PATH", str(tmp_path / "runs.db"))
    monkeypatch.delenv("SCHOOLTRACE_USERS", raising=False)
    monkeypatch.delattr(app.state, "cfo_runtime", raising=False)
    security.SESSIONS.clear(); security.ATTEMPTS.clear()
    with TestClient(app, headers=HEADERS) as client:
        yield client


def import_files(client, ws, files):
    """Stage and commit source files through the real intake endpoints."""
    staged = client.post(f"/api/workspaces/{ws}/imports",
        files=[("files", (f["name"], f["content"].encode(), "text/plain")) for f in files],
        data={"metadata": json.dumps([{"role": f["role"]} for f in files])})
    assert staged.status_code == 201, staged.text
    batch = staged.json()
    committed = client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/commit",
        json={"expected_version": batch["version"], "idempotency_key": batch["id"] + ":" + str(batch["version"])})
    assert committed.status_code == 200, committed.text
    return committed.json()


def start(client):
    """A workspace whose every number came from files uploaded here."""
    created = client.post("/api/workspaces", json={
        "name": "Fictional school district", "start": "2026-09-01", "end": "2026-09-30",
        "scope": "September close: invoice register, budget variance, payroll and grant support."})
    assert created.status_code == 201, created.text
    ws = created.json()["id"]
    # The shared pack now carries its own invoice register. These tests assert on the
    # labelled duplicate cases below, so that role is replaced rather than staged twice
    # under two sources with overlapping record identifiers.
    import_files(client, ws, [f for f in sample_files() if f["role"] != "invoice"] + TRANSACTION_FILES)
    assert client.post(f"/api/workspaces/{ws}/review/scans").status_code == 201
    return ws


def add_service_evidence(client, ws):
    """Commit the withheld service record, which supersedes the snapshot."""
    return import_files(client, ws, [withheld_service_record()])


def view(client, ws):
    response = client.get(f"/api/workspaces/{ws}/review")
    assert response.status_code == 200, response.text
    return response.json()


def invoice(key="I-1", **values):
    return dict(role="invoice", record_key=key, source_id="source-invoices", locator=2,
                payload=dict(vendor_id="V-1", invoice_number="A-1", amount_cents=120000, currency="USD", **values))


@pytest.mark.parametrize("field,value,expected", [
    ("vendor_id", "V-1", 120000), ("vendor_id", "v-1 ", 120000),
    ("vendor_id", "V-2", None), ("invoice_number", "A-2", None),
    ("invoice_number", "A1", None), ("amount_cents", 120001, None),
    ("currency", "CAD", None), ("invoice_number", "a-1 ", 120000),
])
def test_labelled_duplicate_cases(field, value, expected):
    left, right = invoice(), invoice("I-2")
    right["payload"][field] = value
    found = [f for f in checks([left, right], {}) if f["id"].startswith("ap-duplicate-")]
    assert ([f["amount_cents"] for f in found] == ([] if expected is None else [expected]))
    if found:
        assert "does not establish duplicate payment" in found[0]["explanation"]


@pytest.mark.parametrize("actual,budget,amount,status", [(1000000, 900000, 100000, "attention"),
    (900000, 900000, 0, "pass"), (800000, 900000, -100000, "pass"), (1, 0, 1, "attention")])
def test_labelled_budget_cases(actual, budget, amount, status):
    rows = [dict(role="chart", source_id="chart", locator=2, payload=dict(account="5000", type="expense")),
            dict(role="ledger", source_id="ledger", locator=2, payload=dict(account="5000", debit_cents=actual, credit_cents=0)),
            dict(role="budget", source_id="budget", locator=2, payload=dict(account="5000", amount_cents=budget))]
    item = next(f for f in checks(rows, {}) if f["id"].startswith("budget-") and f["amount_cents"] is not None)
    assert (item["amount_cents"], item["status"]) == (amount, status)
    assert {e["source_id"] for e in item["evidence"]} == {"chart", "ledger", "budget"}


def test_budget_versions_not_double_counted():
    rows = [dict(role="chart", source_id="chart", locator=2, payload=dict(account="5000", type="expense")),
            dict(role="ledger", source_id="ledger", locator=2, payload=dict(account="5000", debit_cents=10000, credit_cents=0)),
            dict(role="budget", source_id="budget", locator=2, payload=dict(account="5000", amount_cents=5000))]
    rows.append(deepcopy(rows[-1]))
    item = next(f for f in checks(rows, {}) if f["title"] == "Ambiguous budget versions")
    assert item["status"] == "gap" and item["amount_cents"] is None


def test_empty_records_are_gaps_not_clean_audit():
    assert all(f["status"] == "gap" for f in checks([], {}))


def test_complete_import_scan_evidence_rescan(client):
    ws = start(client)
    before = view(client, ws)
    duplicate = next(f for f in before["findings"] if f["id"].startswith("ap-duplicate-"))
    assert duplicate["amount_cents"] == 120000
    budget = next(f for f in before["findings"] if f["id"].startswith("budget-") and f["amount_cents"] is not None)
    assert budget["amount_cents"] == 100000
    for evidence in duplicate["evidence"]:
        result = client.get(f"/api/workspaces/{ws}/sources/{evidence['source_id']}/spans/{evidence['line']}")
        assert result.status_code == 200 and "VENDOR-1" in result.json()["lines"][0]["text"]
    assert before["live"] is None  # Offline checks never masquerade as model activity.
    add_service_evidence(client, ws)
    stale = view(client, ws)
    assert all(f["stale"] for f in stale["findings"])
    assert client.post(f"/api/workspaces/{ws}/review/scans").status_code == 201
    after = view(client, ws)
    assert after["snapshot_id"] != before["snapshot_id"] and after["changes"]
    support = next(f for f in after["findings"] if f["id"] == "payroll-unsupported-by-service-evidence")
    assert support["amount_cents"] is None and support["status"] == "gap"
    assert "does not judge" in support["explanation"]
    report = client.get(f"/api/workspaces/{ws}/review/report")
    assert report.status_code == 200 and "attachment" in report.headers["content-disposition"]
    assert "USD 1,200.00" in report.text and "Not established" in report.text
    assert after["snapshot_id"] in report.text


def action_body(v):
    return dict(snapshot_id=v["snapshot_id"], finding_id=v["findings"][0]["id"], expected_version=0,
                owner="Finance operations", status="proposed", note="Compare originals before correcting the register.")


def test_human_followup_versioning_decisions_and_staleness(client):
    ws = start(client); v = view(client, ws); body = action_body(v)
    route = f"/api/workspaces/{ws}/review/actions"
    assert client.post(route, json=body | {"status": "approved_proposal"}).status_code == 409
    assert client.post(route, json=body).status_code == 200
    assert client.post(route, json=body).status_code == 409
    assert client.post(route, json=body | {"expected_version": 1, "status": "approved_proposal"}).status_code == 200
    add_service_evidence(client, ws)
    assert client.post(route, json=body | {"expected_version": 2}).status_code == 409
    client.post(f"/api/workspaces/{ws}/review/scans")
    after = view(client, ws)
    assert all(f["follow_up"] is None for f in after["findings"])
    assert len([e for e in after["history"] if e["kind"] == "review.follow_up"]) == 2


def test_evidence_request_persists_without_sending_email(client):
    ws = start(client); v = view(client, ws)
    response = client.post(f"/api/workspaces/{ws}/review/actions", json=action_body(v) | {"status": "evidence_requested"})
    assert response.status_code == 200
    coverage = client.get(f"/api/workspaces/{ws}/coverage").json()
    assert len(coverage["requests"]) == 1 and coverage["requests"][0]["status"] == "open"


def test_standalone_candidates_remain_visible_without_false_verification(client):
    ws = start(client); v = view(client, ws)
    citation = v["findings"][0]["evidence"][0]
    output = {"analysis": {"findings": [{"title": "Candidate observation", "summary": "Needs review", "status": "cleared", "citations": [citation | {"quote": "fictional"}]}]}}
    with db.connect() as c:
        c.execute("INSERT INTO agent_runs (id,ws,agent,snapshot_id,status,model,focus,created_at,output) VALUES (?,?,?,?,?,?,?,?,?)",
                  ("standalone-test", ws, "cfo", v["snapshot_id"], "completed", "test", "test", db.now(), db.encode(output)))
    candidate = next(f for f in view(client, ws)["findings"] if f["origin"] == "standalone_candidate")
    assert candidate["status"] == "attention" and candidate["amount_cents"] is None
    assert "pending" in candidate["review"]


def test_malformed_run_body_is_bounded(client):
    assert client.post("/api/cfo/runs", content="not-json").status_code == 400
    assert client.post("/api/cfo/runs", content="x" * 65537).status_code == 413


def test_expired_sessions_and_bad_passwords_are_denied(client, monkeypatch):
    ws = start(client); configure(monkeypatch, ws)
    assert client.post("/api/access/login", json={"username": "judge", "password": "wrong"}).status_code == 401
    login(client)
    for token, (name, _) in list(security.SESSIONS.items()):
        security.SESSIONS[token] = (name, 0)
    assert client.get(f"/api/workspaces/{ws}/review").status_code == 401


def test_reviewer_can_decide_assigned_workspace_proposal(client, monkeypatch):
    ws = start(client); v = view(client, ws); configure(monkeypatch, ws, "reviewer"); login(client)
    route = f"/api/workspaces/{ws}/review/actions"
    assert client.post(route, json=action_body(v)).status_code == 200
    response = client.post(route, json=action_body(v) | {"expected_version": 1, "status": "approved_proposal"})
    assert response.status_code == 200 and response.json()["actor"] == "judge"


def test_active_run_blocks_workspace_deletion(client):
    ws = start(client); view(client, ws)
    app.state.cfo_runtime.active_workspaces.add(ws)
    assert client.request("DELETE", f"/api/workspaces/{ws}", json={"confirmation": ws}).status_code == 409
    app.state.cfo_runtime.active_workspaces.discard(ws)


def test_live_accepted_claim_projects_and_marks_stale(client):
    ws = start(client); v = view(client, ws)
    repo = app.state.cfo_runtime.repository
    run = Run(id="CFO-projection", request=RunRequest(workspace=ws, mode="live"), status="completed",
              scope=Scope(workspace=ws, snapshot_id=v["snapshot_id"], institution="Fictional", period="September", accounting_profile="demo", sources=[]),
              accepted=[AcceptedClaim(task_id="ap", role="ap", claim=Claim(id="claim", event_key="event", title="Reviewed observation",
                conclusion="A narrow supported claim", disposition="explained", evidence_ids=[v["findings"][0]["evidence"][0]["source_id"]]),
                review=Review(verdict="accept", rationale="Independent evidence read"))])
    repo.save(run)
    projected = next(f for f in view(client, ws)["findings"] if f["origin"] == "live_agent")
    assert projected["review"] == "Independent evidence read" and not projected["stale"]
    add_service_evidence(client, ws)
    assert view(client, ws)["live_stale"]
    run.status = "running"; repo.save(run)
    assert not any(f["origin"] == "live_agent" for f in view(client, ws)["findings"])


def test_delete_workspace_removes_source_reviews_and_runs(client):
    ws = start(client); v = view(client, ws)
    app.state.cfo_runtime.repository.save(Run(id="CFO-delete", request=RunRequest(workspace=ws)))
    assert client.request("DELETE", f"/api/workspaces/{ws}", json={"confirmation": "wrong"}).status_code == 422
    result = client.request("DELETE", f"/api/workspaces/{ws}", json={"confirmation": ws})
    assert result.status_code == 200, result.text
    assert client.get(f"/api/workspaces/{ws}/review").status_code == 404
    with pytest.raises(KeyError): app.state.cfo_runtime.repository.get("CFO-delete")
    with db.connect() as c:
        for table in ("sources", "snapshots", "review_scans", "events"):
            assert c.execute(f"SELECT count(*) FROM {table} WHERE ws=?", (ws,)).fetchone()[0] == 0


@pytest.mark.parametrize("origin", ["https://evil.example", "null", "http://localhost:9000"])
def test_untrusted_browser_origins_denied(client, origin):
    body = {"name": "Blocked", "start": "2026-09-01", "end": "2026-09-30", "scope": "Should never be created"}
    assert client.post("/api/workspaces", headers={"Origin": origin}, json=body).status_code == 403


def test_dns_rebinding_host_denied(client):
    assert client.get("/api/workspaces", headers={"Host": "evil.example"}).status_code == 403


def configure(monkeypatch, ws, role="viewer"):
    monkeypatch.setenv("SCHOOLTRACE_USERS", json.dumps({"judge": {"password_hash": security.password_hash("correct horse demo"), "role": role, "workspaces": [ws]}}))


def login(client):
    response = client.post("/api/access/login", json={"username": "judge", "password": "correct horse demo"})
    assert response.status_code == 200, response.text
    assert "HttpOnly" in response.headers["set-cookie"] and "SameSite=strict" in response.headers["set-cookie"]


def test_authentication_workspace_acl_and_logout(client, monkeypatch):
    ws = start(client); foreign = start(client); configure(monkeypatch, ws)
    assert client.get(f"/api/workspaces/{ws}/review").status_code == 401
    login(client)
    assert [w["id"] for w in client.get("/api/workspaces").json()] == [ws]
    assert client.get(f"/api/workspaces/{foreign}/review").status_code == 403
    assert client.get(f"/api/workspaces/{ws}/review").status_code == 200
    assert client.post(f"/api/workspaces/{ws}/review/scans").status_code == 403
    # Viewers must be able to sign out despite being forbidden financial writes.
    assert client.post("/api/access/logout").status_code == 200
    assert client.get(f"/api/workspaces/{ws}/review").status_code == 401


def test_analyst_cannot_approve_or_delete(client, monkeypatch):
    ws = start(client); v = view(client, ws); configure(monkeypatch, ws, "analyst"); login(client)
    route = f"/api/workspaces/{ws}/review/actions"
    assert client.post(route, json=action_body(v)).status_code == 200
    assert client.post(route, json=action_body(v) | {"expected_version": 1, "status": "approved_proposal"}).status_code == 403
    assert client.request("DELETE", f"/api/workspaces/{ws}", json={"confirmation": ws}).status_code == 403
    assert client.post("/api/workspaces", json={"name": "New", "start": "2026-09-01", "end": "2026-09-30",
                                                "scope": "Analysts cannot create workspaces"}).status_code == 403


def test_auth_config_errors_fail_closed(client, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_USERS", "not-json")
    assert client.get("/api/workspaces").status_code == 503


def test_live_run_workspace_acl_cannot_be_bypassed(client, monkeypatch):
    ws = start(client); foreign = start(client)
    view(client, ws)
    app.state.cfo_runtime.repository.save(Run(id="CFO-foreign", request=RunRequest(workspace=foreign)))
    configure(monkeypatch, ws, "analyst"); login(client)
    assert client.get("/api/cfo/runs/CFO-foreign").status_code == 403
    assert client.get("/api/cfo/runs/CFO-foreign/report").status_code == 403
    assert client.post("/api/cfo/runs", json={"workspace": foreign, "mode": "live"}).status_code == 403


def test_management_amounts_available_to_live_evidence_gateway(client):
    import asyncio
    from app.integrations.cfo_intake import IntakeDataSource
    ws = start(client)
    async def exercise():
        data = IntakeDataSource(); scope = await data.snapshot(ws)
        duplicate = next(c for c in scope.calculations if c.id.startswith("ap-duplicate-"))
        amount = await data.calculate(scope, duplicate.id)
        assert amount.amount_cents == 120000 and amount.cash_delta_cents == 0
    asyncio.run(exercise())


@pytest.mark.skipif(os.getenv("RUN_DIRECTOR_LIVE") != "1", reason="Explicit opt-in paid fictional demo smoke")
def test_live_director_demo_end_to_end(client, monkeypatch):
    import asyncio
    monkeypatch.setenv("CFO_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("SPECIALIST_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("CFO_PROVIDER", "openai")
    monkeypatch.setenv("SPECIALIST_PROVIDER", "openai")
    ws = start(client)
    result = client.post("/api/cfo/runs", json={"workspace": ws, "mode": "live", "workflow": "five_agent",
        "objective": "Review this fictional school district. Plan exactly one independent task per specialist, with no task dependencies. AP should test duplicate invoice candidates using the engine; Payroll should examine expense budget variance; Grants should identify missing service support. Return at most one narrow claim per specialist plus evidence requests. All values are fictional. No payment or approval is implied.",
        "limits": {"call_timeout_s": 180}})
    assert result.status_code == 202, result.text
    async def finish():
        await asyncio.gather(*list(app.state.cfo_runtime.pending.values()))
    client.portal.call(finish)
    unified = view(client, ws); run = unified["live"]
    assert run["status"] in {"completed", "needs_evidence"}, run["unresolved"]
    assert {t["spec"]["role"] for t in run["tasks"]} == {"ap", "py", "gr"}
    assert all(t["attempts"] for t in run["tasks"])
    assert any(e["actor"] == "au" and e["action"].startswith("review.") for e in run["events"])
    assert len([f for f in unified["findings"] if f["origin"] == "live_agent"]) == len(run["accepted"])
    assert client.get(f"/api/workspaces/{ws}/review/report").status_code == 200
    print(f"DIRECTOR LIVE: status={run['status']} accepted={len(run['accepted'])} tasks={len(run['tasks'])} evidence_calls={run['tool_calls']} CFO_calls={run['model_calls']}")


def _invoice(record_key, source_id, line, number="INV-2291", amount=120000):
    """One invoice row in the shape review.checks() consumes."""
    return {
        "role": "invoice", "record_key": record_key, "source_id": source_id, "locator": line,
        "payload": {"vendor_id": "VEND-1", "invoice_number": number,
                    "amount_cents": amount, "currency": "USD",
                    "po_id": "PO-1", "receipt_id": "RC-1"},
    }


def _ap_duplicate_ids(records):
    from app.accounting.review import checks
    return [c["id"] for c in checks(records, {}) if c["id"].startswith("ap-duplicate-")]


def test_ap_duplicate_id_survives_a_third_invoice_joining_the_group():
    """The id must name the duplicate, not who is currently in it.

    It used to hash the group's record_keys, so a third matching invoice
    retired the old id and minted a new one. A reviewer's follow-up is scoped
    by (finding_id, snapshot_id), so the note orphaned and the unresolved
    duplicate came back looking brand new — and the changes diff keys on id
    alone, so it reported nothing had changed.
    """
    pair = [_invoice("R1", "S1", 2), _invoice("R2", "S1", 3)]
    trio = pair + [_invoice("R3", "S2", 9)]

    before, after = _ap_duplicate_ids(pair), _ap_duplicate_ids(trio)
    assert len(before) == len(after) == 1
    assert before == after, "a third invoice joining the group must not move the finding id"


def test_ap_duplicate_ids_still_separate_distinct_duplicates():
    """Stability must not collapse two different duplicates onto one id."""
    records = [
        _invoice("R1", "S1", 2, number="INV-1"), _invoice("R2", "S1", 3, number="INV-1"),
        _invoice("R3", "S1", 4, number="INV-2"), _invoice("R4", "S1", 5, number="INV-2"),
    ]
    assert len(set(_ap_duplicate_ids(records))) == 2
