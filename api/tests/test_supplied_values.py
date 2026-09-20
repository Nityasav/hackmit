"""Supplying a value a document never stated, before an import is committed.

An extracted register can be missing a field the document simply does not
contain: an invoice names a vendor but carries no vendor id, and a register
that requires one cannot be committed. The id exists — it is just not on the
page — so somebody has to supply it, and there was no way to.

The line this draws is the point of the feature. Filling a blank is
bookkeeping. Rewriting what a source states is altering evidence, and must not
be reachable from a review screen.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import db, ingestion
from app.main import app
from tests.conftest import HEADERS

HEADER = "record_id,vendor_id,invoice_number,invoice_date,due_date,amount\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    with TestClient(app, headers=HEADERS) as test_client:
        yield test_client


def _staged(client, rows: str):
    ws = client.post("/api/workspaces", json={
        "name": "Fictional SaaS company", "start": "2026-09-01", "end": "2026-09-30",
        "scope": "September close"}).json()["id"]
    batch = client.post(f"/api/workspaces/{ws}/imports",
                        files=[("files", ("vendor_invoices.csv", (HEADER + rows).encode(), "text/csv"))],
                        data={"metadata": json.dumps([{"role": "vendor_invoices"}])}).json()
    return ws, batch


def test_a_missing_value_can_be_supplied_and_the_import_revalidates(client):
    ws, batch = _staged(client, "VI-1,,INV-100,2026-09-08,2026-09-23,1200.00\n")
    assert batch["counts"]["issues"] == 1, batch["issues"]

    response = client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/values", json={
        "expected_version": batch["version"], "source_id": batch["files"][0]["id"],
        "edits": [{"locator": 2, "field": "vendor_id", "value": "V-1"}],
        "note": "The invoice names the vendor but carries no id; matched to the vendor register."})

    assert response.status_code == 200, response.text
    after = response.json()
    assert after["counts"]["issues"] == 0
    assert after["counts"]["valid_records"] == 1
    assert after["files"][0]["preview"][0]["payload"]["vendor_id"] == "V-1"


def test_a_value_the_source_states_is_never_overwritten(client):
    """The safety property. Supplying what a document omitted and rewriting
    what it says are different acts, and a review screen may only do the
    first."""
    ws, batch = _staged(client, "VI-1,V-1,INV-100,2026-09-08,2026-09-23,1200.00\n")

    response = client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/values", json={
        "expected_version": batch["version"], "source_id": batch["files"][0]["id"],
        "edits": [{"locator": 2, "field": "vendor_id", "value": "V-999"}],
        "note": "trying to change a stated value"})

    assert response.status_code == 409
    assert "never overwritten" in response.json()["detail"]["message"]


def test_supplying_a_value_records_who_supplied_it(client):
    """The trail has to distinguish a value read off a page from one a person
    asserted, or the register cannot be defended later."""
    ws, batch = _staged(client, "VI-1,,INV-100,2026-09-08,2026-09-23,1200.00\n")
    client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/values", json={
        "expected_version": batch["version"], "source_id": batch["files"][0]["id"],
        "edits": [{"locator": 2, "field": "vendor_id", "value": "V-1"}],
        "note": "Matched by vendor name against the vendor register."})

    with db.connect() as connection:
        event = connection.execute(
            "SELECT actor, payload FROM events WHERE ws=? AND kind='values_supplied'", (ws,)).fetchone()
    payload = json.loads(event["payload"])
    assert event["actor"]
    assert payload["supplied"] == [{"line": 2, "field": "vendor_id", "value": "V-1"}]
    assert "vendor register" in payload["note"]


def test_an_unknown_column_or_line_is_refused(client):
    ws, batch = _staged(client, "VI-1,,INV-100,2026-09-08,2026-09-23,1200.00\n")
    body = {"expected_version": batch["version"], "source_id": batch["files"][0]["id"], "note": "n"}

    bad_field = client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/values",
                            json={**body, "edits": [{"locator": 2, "field": "nope", "value": "x"}]})
    bad_line = client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/values",
                           json={**body, "edits": [{"locator": 99, "field": "vendor_id", "value": "x"}]})

    assert bad_field.status_code == 422 and "not a column" in bad_field.json()["detail"]["message"]
    assert bad_line.status_code == 422 and "not a row" in bad_line.json()["detail"]["message"]


def test_a_stale_preview_is_refused(client):
    """The same optimistic lock the mapping patch uses: someone else may have
    revalidated since this screen was drawn."""
    ws, batch = _staged(client, "VI-1,,INV-100,2026-09-08,2026-09-23,1200.00\n")
    response = client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/values", json={
        "expected_version": batch["version"] + 5, "source_id": batch["files"][0]["id"],
        "edits": [{"locator": 2, "field": "vendor_id", "value": "V-1"}], "note": "n"})
    assert response.status_code == 409


def test_a_committed_import_cannot_be_edited(client):
    ws, batch = _staged(client, "VI-1,V-1,INV-100,2026-09-08,2026-09-23,1200.00\n")
    committed = client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/commit",
                            json={"expected_version": batch["version"], "idempotency_key": batch["id"]})
    assert committed.status_code == 200, committed.text

    response = client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/values", json={
        "expected_version": committed.json()["version"], "source_id": batch["files"][0]["id"],
        "edits": [{"locator": 2, "field": "invoice_number", "value": "INV-999"}], "note": "n"})

    assert response.status_code == 409
    assert "new revision" in response.json()["detail"]["message"]
