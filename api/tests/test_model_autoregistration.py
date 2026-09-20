"""Every workspace can read a PDF the server is configured to read.

Which extractors exist is a property of the server: `SCHOOLTRACE_EXTRACTORS`
names them and `model_config` re-validates one on every call. Requiring a
separate registration per workspace therefore guarded nothing, and a new
company could upload a PDF and find the lab quietly unable to read it with no
indication that registration was the missing step.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app
from tests.conftest import HEADERS

ARTIFACT = "a" * 64
MANIFEST = hashlib.sha256(b"").hexdigest()


def _extractors(endpoint="http://127.0.0.1:8901/extract", artifact=ARTIFACT):
    return json.dumps({"nuextract3-local": {
        "endpoint": endpoint, "artifact_sha256": artifact,
        "base_revision": "rev-1", "training_document_hashes": [],
        "training_manifest_sha256": MANIFEST, "training_groups": [],
        "supported_roles": ["invoice", "policy"]}})


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SCHOOLTRACE_EXTRACTORS", _extractors())
    with TestClient(app, headers=HEADERS) as test_client:
        yield test_client


def _workspace(client):
    return client.post("/api/workspaces", json={
        "name": "Fictional SaaS company", "start": "2026-09-01",
        "end": "2026-09-30", "scope": "September close"}).json()["id"]


def test_a_new_company_can_read_a_pdf_without_anyone_registering_a_model(client):
    ws = _workspace(client)

    state = client.get(f"/api/workspaces/{ws}/extraction").json()

    assert [m["name"] for m in state["model"]] == ["nuextract3-local"]
    # Selectable, not the silent default: promoting one still goes through the
    # policy gate, which is where "is it good enough" is actually decided.
    assert state["active"] is None


def test_registering_says_nobody_evaluated_it_here(client):
    """A registration that arrived from configuration must not read as one a
    reviewer made."""
    ws = _workspace(client)
    model = client.get(f"/api/workspaces/{ws}/extraction").json()["model"][0]
    assert "Nobody has evaluated it here" in model["note"]

    with db.connect() as connection:
        event = connection.execute(
            "SELECT actor FROM events WHERE ws=? AND kind='extraction.model'", (ws,)).fetchone()
    assert event["actor"] == "server configuration"


def test_it_does_not_register_the_same_model_twice(client):
    ws = _workspace(client)
    for _ in range(3):
        state = client.get(f"/api/workspaces/{ws}/extraction").json()
    assert len(state["model"]) == 1


def test_a_moved_extractor_is_reregistered_under_its_current_config(client, monkeypatch):
    """A registration records the exact weights and endpoint it was made
    against, so restarting the extractor elsewhere leaves the old row naming
    weights nobody is serving and `infer` refuses it. That refusal is correct;
    needing a person to know the remedy was not."""
    ws = _workspace(client)
    before = client.get(f"/api/workspaces/{ws}/extraction").json()["model"][0]

    monkeypatch.setenv("SCHOOLTRACE_EXTRACTORS", _extractors(artifact="b" * 64))
    after = client.get(f"/api/workspaces/{ws}/extraction").json()["model"]

    assert len(after) == 2, "the old registration is kept as the record of what was served"
    assert after[-1]["config_hash"] != before["config_hash"]


def test_a_retired_model_is_not_quietly_brought_back(client):
    """Retiring one is a decision. Configuration must not undo it."""
    ws = _workspace(client)
    model = client.get(f"/api/workspaces/{ws}/extraction").json()["model"][0]
    with db.connect() as connection:
        from app import extraction as ex
        ex.put(connection, ws, "retirement", {"model_id": model["id"], "reason": "superseded"}, "a reviewer")

    state = client.get(f"/api/workspaces/{ws}/extraction").json()
    live = [m for m in state["model"]
            if m["id"] not in {r["model_id"] for r in state["retirement"]}]
    assert [m["config_hash"] for m in live] == [model["config_hash"]], \
        "a retired model must not reappear under the same configuration"


def test_a_broken_extractor_entry_does_not_break_the_screen(client, monkeypatch):
    """A configuration that does not validate is skipped, not raised: one bad
    entry should not take the whole documents screen down."""
    monkeypatch.setenv("SCHOOLTRACE_EXTRACTORS", json.dumps({"broken": {"endpoint": "http://evil.example/"}}))
    ws = _workspace(client)

    response = client.get(f"/api/workspaces/{ws}/extraction")

    assert response.status_code == 200
    assert response.json()["model"] == []
