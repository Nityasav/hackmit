"""Run-scoped report truthfulness; no paid provider calls."""
import json
import pypdfium2
from app import db
from tests.test_chat import client, ws, _scripted  # noqa: F401


def start(client, ws, monkeypatch, disposition="clear"):
    _scripted(monkeypatch, disposition)
    result = client.post(f"/api/workspaces/{ws}/chat", json={"message": "Assess this company's books.", "full_review": True})
    assert result.status_code == 201, result.text
    return result.json()["thread_id"]


def test_audit_report_is_scoped_to_the_run_and_its_saved_scan(client, ws, monkeypatch):
    thread = start(client, ws, monkeypatch)
    path = f"/api/workspaces/{ws}/audit-reports/{thread}"
    report = client.get(path).json()
    assert report["workspace"]["name"] == "Halden Cloud Inc."
    assert report["scan"]["record_count"] > 0
    assert sum(d["total"] for d in report["domains"]) == 17
    assert any(d["not_assessed"] for d in report["domains"])
    assert "overall financial health" in report["executive_summary"]
    with db.connect() as c:
        assert report["run_id"] != thread
        assert all(f["id"] in {r[0] for r in c.execute("SELECT id FROM agent_decisions WHERE ws=? AND thread_id=?", (ws, report["run_id"]))}
                   for f in report["findings"] if f["origin"] == "agent")
    client.post(f"/api/workspaces/{ws}/review/scans")
    assert client.get(path).json()["scan"]["id"] == report["scan"]["id"]
    pdf = client.get(path + "/pdf")
    assert pdf.status_code == 200, pdf.text
    doc = pypdfium2.PdfDocument(pdf.content)
    text = " ".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert "Financial audit review" in text and "Executive assessment" in text
    assert "Halden Cloud Inc." in text and "Review coverage" in text
    assert client.get(f"/api/workspaces/not-this-company/audit-reports/{thread}").status_code == 404


def test_waiting_is_partial_and_approval_does_not_erase_evidence_gaps(client, ws, monkeypatch):
    thread = start(client, ws, monkeypatch, "insufficient")
    report = client.get(f"/api/workspaces/{ws}/audit-reports/{thread}").json()
    assert report["status"] == "waiting_on_you"
    assert "incomplete" in report["headline"]
    assert report["counts"]["pending"] > 0
    assert report["counts"]["gap"] > 0


def test_running_and_non_audit_conversations_are_not_finished_reports(client, ws):
    from app.agents.chat import _record
    with db.connect() as c:
        for thread, audit in [("running-audit", True), ("ordinary-question", False)]:
            for role, body, status in [("person", {"text": "Question", "full_review": audit}, "sent"), ("orchestrator", {"text": "Working"}, "running")]:
                _record(c, ws, {"id": db.uid("turn"), "thread_id": thread, "role": role, "body": body, "status": status, "created_at": db.now()})
    assert client.get(f"/api/workspaces/{ws}/audit-reports/running-audit").status_code == 409
    assert client.get(f"/api/workspaces/{ws}/audit-reports/ordinary-question").status_code == 404


def test_legacy_audit_does_not_borrow_latest_scan(client, ws, monkeypatch):
    thread = start(client, ws, monkeypatch)
    with db.connect() as c:
        row = c.execute("SELECT id,body FROM conversations WHERE ws=? AND thread_id=? AND role='person'", (ws, thread)).fetchone()
        c.execute("UPDATE conversations SET body=? WHERE id=?", (json.dumps({"text": json.loads(row["body"])["text"]}), row["id"]))
    report = client.get(f"/api/workspaces/{ws}/audit-reports/{thread}").json()
    assert report["legacy"] is True
    assert report["scan"] is None
    assert any("unrelated scans are excluded" in line for line in report["unresolved"])
