"""Regression tests for removal, PDF export, and human continuation. No paid calls."""
import asyncio

from app import db, graph, projection
from app.agents.continuation import resolve
from tests.test_ingestion import client, create, upload, commit  # noqa: F401
from tests.test_escalation import ws, _run, _escalating_model  # noqa: F401


def test_remove_source_updates_snapshot_and_keeps_original(client):
    workspace = create(client)
    batch = upload(client, workspace)
    commit(client, workspace, batch)
    coverage = client.get(f"/api/workspaces/{workspace}/coverage").json()
    source = next(s for s in coverage["sources"] if s["role"] == "ledger")
    path = f"/api/workspaces/{workspace}/sources/{source['id']}"
    original = client.get(path + "/download").content
    body = {"expected_revision": coverage["workspace"]["revision"], "confirmation": source["name"]}
    assert client.request("DELETE", path, json={**body, "confirmation": "wrong"}).status_code == 422
    assert client.request("DELETE", path, json={**body, "expected_revision": -1}).status_code == 409
    removed = client.request("DELETE", path, json=body)
    assert removed.status_code == 200, removed.text
    assert removed.json()["removed_records"] == 8
    after = client.get(f"/api/workspaces/{workspace}/coverage").json()
    assert after["counts"].get("ledger", 0) == 0
    assert after["snapshot"]["id"] != coverage["snapshot"]["id"]
    assert client.get(path + "/download").content == original
    other = create(client)
    assert client.request("DELETE", f"/api/workspaces/{other}/sources/{source['id']}", json=body).status_code == 404


def test_pdf_download_is_pdf_not_markdown(client):
    workspace = create(client, name="Test <school> & records")
    commit(client, workspace, upload(client, workspace))
    assert client.post(f"/api/workspaces/{workspace}/review/scans").status_code == 201
    response = client.get(f"/api/workspaces/{workspace}/review/report.pdf")
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF-")
    assert response.headers["content-type"] == "application/pdf"
    assert len(response.content) > 1500


def test_remove_requires_reviewer(client):
    workspace = create(client)
    result = client.request("DELETE", f"/api/workspaces/{workspace}/sources/missing",
                            headers={"X-SchoolTrace-Reviewer": ""},
                            json={"expected_revision": 0, "confirmation": "missing"})
    assert result.status_code == 403


def test_common_approval_resumes_graph_and_resolves_task(ws, monkeypatch):
    paused = _run(ws, _escalating_model())
    question = paused["waiting_on_you"][0]
    original = graph.resume_investigation
    async def resume(*args, **kwargs):
        return await original(*args, **kwargs, client=_escalating_model())
    monkeypatch.setattr(graph, "resume_investigation", resume)
    outcome = asyncio.run(resolve(ws, question["approval_id"], "approved"))
    assert question["approval_id"] not in {q["approval_id"] for q in outcome.get("waiting_on_you", [])}
    with db.connect() as connection:
        approval = dict(connection.execute("SELECT * FROM approvals WHERE id=?", (question["approval_id"],)).fetchone())
        decision = dict(connection.execute("SELECT * FROM agent_decisions WHERE id=?", (approval["finding_id"],)).fetchone())
        related = [dict(r) for r in connection.execute("SELECT * FROM approvals WHERE ws=? AND finding_id=?", (ws, decision["id"]))]
    assert all(a["status"] == "approved" for a in related)
    assert projection._legacy_tasks([decision], related)[0]["column"] == "done"
