"""Synthetic lifecycle/security tests; mock inference scores are not model benchmarks."""
import copy
import io
import json

import pytest
from fastapi.testclient import TestClient

from app import db, extraction as ex, ingestion, security
from app.main import app

from tests.conftest import sample_files, withheld_service_record


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CFO_DB_PATH", str(tmp_path / "cfo.db"))
    monkeypatch.delenv("SCHOOLTRACE_USERS", raising=False)
    monkeypatch.delattr(app.state, "cfo_runtime", raising=False)
    security.SESSIONS.clear()
    with TestClient(app, headers={"X-SchoolTrace-Reviewer": "local-reviewer"}) as client:
        yield client


def workspace(client):
    return client.post("/api/workspaces", json={"name": "Extraction test", "start": "2026-09-01", "end": "2026-09-30", "scope": "Synthetic extraction"}).json()["id"]


def path(ws):
    return f"/api/workspaces/{ws}/extraction"


def commit_files(client, ws, files):
    """Stage and commit files through the real intake endpoints."""
    staged = client.post(f"/api/workspaces/{ws}/imports",
        files=[("files", (f["name"], f["content"].encode(), "text/plain")) for f in files],
        data={"metadata": json.dumps([{"role": f["role"]} for f in files])})
    assert staged.status_code == 201, staged.text
    batch = staged.json()
    committed = client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/commit",
        json={"expected_version": batch["version"], "idempotency_key": batch["id"] + ":" + str(batch["version"])})
    assert committed.status_code == 200, committed.text
    return committed.json()


def reviewed_workspace(client):
    """A workspace holding committed records and a rules scan of them.

    Every record here was uploaded by this test through the import endpoints, so
    the counts below are the engine's count of bytes the test supplied.
    """
    ws = workspace(client)
    commit_files(client, ws, sample_files())
    assert client.post(f"/api/workspaces/{ws}/review/scans").status_code == 201
    return ws


def upload(client, ws, text="Invoice A-101 vendor V-1 amount 1200.00 dated 2026-09-01 due 2026-10-01 currency USD", role="invoice"):
    response = client.post(path(ws) + "/documents", files={"file": ("invoice.txt", text.encode(), "text/plain")}, data={"role": role})
    assert response.status_code == 201, response.text
    return response.json()


def output(doc):
    record = {key: {"status": "missing", "value": None, "page": None, "start": None, "end": None} for key in ex.schema(doc["role"])}
    text = doc["pages"][0]["text"]
    for key, value in {"invoice_number": "A-101", "vendor_id": "V-1", "amount": "1200.00",
                             "invoice_date": "2026-09-01", "due_date": "2026-10-01", "currency": "USD"}.items():
        if key in record and value in text:
            start = text.index(value)
            record[key] = {"status": "present", "value": value, "page": 1, "start": start, "end": start + len(value)}
    return {"schema_version": ex.SCHEMA_VERSION, "records": [record]}


def correction(client, ws, doc, group="vendor-template-a", consent=True, **changes):
    body = {"document_id": doc["id"], "output": output(doc), "group": group, "training_authorized": consent,
            "authorization_note": "Synthetic fixture owned by test", "note": "Compared against original", "text_sha256": doc["text_sha256"], **changes}
    response = client.post(path(ws) + "/corrections", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def freeze(client, ws, corrections, purpose="train"):
    return client.post(path(ws) + "/datasets", json={"name": "v1", "purpose": purpose, "correction_ids": [c["id"] for c in corrections]})


def configure(monkeypatch, **changes):
    models = {name: {"endpoint": "http://127.0.0.1:8901/extract", "artifact_sha256": char * 64,
                    "base_revision": "immutable-test-revision", "training_manifest_sha256": "f" * 64,
                    "training_document_hashes": [], "training_groups": [], "supported_roles": ["invoice"]}
              for name, char in [("base", "a"), ("candidate", "b"), ("next", "c")]}
    models["candidate"].update(changes)
    monkeypatch.setenv("SCHOOLTRACE_EXTRACTORS", json.dumps(models))
    return models


def register(client, ws, name):
    response = client.post(path(ws) + "/models", json={"name": name, "note": "Synthetic test adapter"})
    assert response.status_code == 201, response.text
    return response.json()


def test_text_upload_idempotent_and_scoped(client):
    ws, other = workspace(client), workspace(client)
    doc = upload(client, ws)
    assert upload(client, ws)["id"] == doc["id"]
    assert client.get(path(other) + f"/documents/{doc['id']}/original").status_code == 404
    assert client.get(path(ws) + f"/documents/{doc['id']}/original").content.startswith(b"Invoice")
    assert client.get(path(ws)).json()["documents"][0]["pages"][0]["method"] == "native"
    assert client.get(f"/api/workspaces/{ws}/updates").json()["total_records"] == 0


@pytest.mark.parametrize("mutation", ["invented", "offset", "page", "extra", "missing_key", "missing_value", "float"])
def test_invalid_extractions_rejected(client, mutation):
    ws = workspace(client); doc = upload(client, ws); out = output(doc); field = out["records"][0]["amount"]
    if mutation == "invented": field["value"] = "9999.00"
    elif mutation == "offset": field["start"] += 1
    elif mutation == "page": field["page"] = 2
    elif mutation == "extra": out["records"][0]["secret"] = field
    elif mutation == "missing_key": del out["records"][0]["vendor_id"]
    elif mutation == "missing_value": field["status"] = "missing"
    elif mutation == "float": field["value"] = 1200.0
    response = client.post(path(ws) + "/corrections", json={"document_id": doc["id"], "output": out, "group": "x", "authorization_note": "synthetic", "note": "checked", "text_sha256": doc["text_sha256"]})
    assert response.status_code == 422


def test_consent_versions_freeze_and_withdrawal(client):
    ws = workspace(client); doc = upload(client, ws)
    c1 = correction(client, ws, doc, consent=False)
    assert freeze(client, ws, [c1]).status_code == 409
    c2 = correction(client, ws, doc, expected_previous=c1["id"])
    response = freeze(client, ws, [c2]); assert response.status_code == 201
    dataset = response.json()
    export = client.get(path(ws) + f"/datasets/{dataset['id']}/training.jsonl")
    assert export.status_code == 200
    assert json.loads(export.text)["output"] == output(doc)
    assert freeze(client, ws, [c2], "evaluation").status_code == 409
    c3 = correction(client, ws, doc, consent=False, expected_previous=c2["id"])
    assert c3["id"] != c2["id"]
    assert client.get(path(ws) + f"/datasets/{dataset['id']}/training.jsonl").status_code == 409
    stale = {**c2, "expected_previous": c1["id"]}
    for key in ("id", "created_at", "source_sha256", "actor"): stale.pop(key, None)
    assert client.post(path(ws) + "/corrections", json=stale).status_code == 409


def test_group_split_and_gold_export_block(client):
    ws = workspace(client); first = upload(client, ws); second = upload(client, ws, "Different invoice A-101 V-1 1200.00 2026-09-01 USD")
    a = correction(client, ws, first, group="Template A")
    b = correction(client, ws, second, group=" template a ")
    assert freeze(client, ws, [a], "evaluation").status_code == 201
    assert freeze(client, ws, [b], "train").status_code == 409
    data = client.get(path(ws)).json()["dataset"][0]
    assert client.get(path(ws) + f"/datasets/{data['id']}/training.jsonl").status_code == 403


def test_transcription_invalidates_labels_and_datasets(client):
    ws = workspace(client); doc = upload(client, ws); reviewed = correction(client, ws, doc)
    data = freeze(client, ws, [reviewed]).json()
    response = client.post(path(ws) + f"/documents/{doc['id']}/transcription", json={"expected_text_sha256": doc["text_sha256"], "pages": ["Corrected invoice text"], "note": "Compared original"})
    assert response.status_code == 200
    assert client.get(path(ws) + f"/datasets/{data['id']}/training.jsonl").status_code == 409
    assert client.post(path(ws) + "/stage", json={"correction_id": reviewed["id"]}).status_code == 409
    assert client.get(path(ws) + f"/documents/{doc['id']}/original").content.startswith(b"Invoice")


def test_staging_requires_review_defaults_to_evidence_and_no_auto_commit(client):
    ws = workspace(client); doc = upload(client, ws)
    assert client.post(path(ws) + "/stage", json={"correction_id": doc["id"]}).status_code == 404
    reviewed = correction(client, ws, doc)
    staged = client.post(path(ws) + "/stage", json={"correction_id": reviewed["id"]}).json()
    again = client.post(path(ws) + "/stage", json={"correction_id": reviewed["id"]}).json()
    assert again["batch_id"] == staged["batch_id"]
    batch = ingestion.get_batch(ws, staged["batch_id"])
    # Staged under what the document IS, not the catch-all. An agent may read
    # only roles it declared it needs, so everything landing in `document` meant
    # a person checked every value and no agent could then read any of it.
    assert len(batch["files"]) == 1 and batch["files"][0]["options"]["role"] == "invoice"
    assert client.get(f"/api/workspaces/{ws}/updates").json()["total_records"] == 0
    financial = client.post(path(ws) + "/stage", json={"correction_id": reviewed["id"], "include_records": True}).json()
    batch = ingestion.get_batch(ws, financial["batch_id"])
    assert batch["status"] == "ready_to_commit"
    assert len(batch["files"]) == 2
    origin = ingestion.source_view(ws, batch["files"][1]["id"])["extraction_origin"]
    assert origin["document_id"] == doc["id"] and origin["sha256"] == doc["sha256"]
    committed = ingestion.commit(ws, batch["id"], ingestion.CommitRequest(expected_version=batch["version"], idempotency_key="one"))
    assert committed["snapshot_id"]
    assert client.get(f"/api/workspaces/{ws}/updates").json()["total_records"] == 2


def test_adapter_contract_does_not_send_gold(client, monkeypatch):
    ws = workspace(client); doc = upload(client, ws); configure(monkeypatch); model = register(client, ws, "candidate")
    seen = []
    def handler(request):
        body = json.loads(request.content); seen.append(body)
        assert "output" not in body and "correction" not in body and "dataset" not in body
        return __import__("httpx").Response(200, json={"artifact_sha256": "b" * 64, "output": output(doc)})
    import httpx
    original = httpx.Client
    monkeypatch.setattr(ex.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    result = client.post(path(ws) + "/predict", json={"document_id": doc["id"], "model_id": model["id"]}).json()
    assert result["error"] is None and result["output"] == output(doc)
    assert len(seen) == 1


@pytest.mark.parametrize("endpoint", ["https://example.com/extract", "http://localhost:8901/extract", "http://169.254.169.254/", "http://127.0.0.1@evil.com/", "file:///secret"])
def test_model_endpoint_restrictions(client, monkeypatch, endpoint):
    ws = workspace(client); configure(monkeypatch, endpoint=endpoint)
    assert client.post(path(ws) + "/models", json={"name": "candidate", "note": "Test"}).status_code == 503


def test_benchmark_gate_promotion_rollback_retire(client, monkeypatch):
    ws = workspace(client); configure(monkeypatch)
    # Fast synthetic preprocessing for the lifecycle test; real OCR has a separate test.
    monkeypatch.setattr(ex.document_processing, "process", lambda data, suffix: [{"page": 1, "text": data.decode(), "method": "native", "warnings": []}])
    corrections = [correction(client, ws, upload(client, ws, f"Fixture {i} A-101 V-1 1200.00 2026-09-01 USD"), group=f"heldout-{i % 3}") for i in range(20)]
    dataset = freeze(client, ws, corrections, "evaluation").json()
    base, candidate, next_model = [register(client, ws, name) for name in ("base", "candidate", "next")]
    monkeypatch.setattr(ex, "infer", lambda model, doc: (output(doc), 0.01))
    evaluated = client.post(path(ws) + "/benchmarks", json={"dataset_id": dataset["id"], "baseline_id": base["id"], "candidate_id": candidate["id"]})
    assert evaluated.status_code == 201, evaluated.text
    evaluated = evaluated.json(); assert evaluated["passed"], evaluated["failures"]
    assert evaluated["runs"][candidate["id"]]["metrics"]["present_fields"] == 100
    promoted = client.post(path(ws) + "/promote", json={"evaluation_id": evaluated["id"], "expected_version": 0, "note": "Approve test release"})
    assert promoted.status_code == 200
    assert client.post(path(ws) + "/promote", json={"evaluation_id": evaluated["id"], "expected_version": 0, "note": "Stale"}).status_code == 409
    ev2 = client.post(path(ws) + "/benchmarks", json={"dataset_id": dataset["id"], "baseline_id": candidate["id"], "candidate_id": next_model["id"]}).json()
    assert client.post(path(ws) + "/promote", json={"evaluation_id": ev2["id"], "expected_version": 1, "note": "Approve next"}).status_code == 200
    assert client.post(path(ws) + "/rollback", json={"release_id": promoted.json()["id"], "expected_version": 2, "note": "Rollback test"}).status_code == 200
    assert client.get(path(ws)).json()["active"]["model_id"] == candidate["id"]
    assert client.post(path(ws) + "/retire", json={"model_id": candidate["id"], "note": "Cannot retire active"}).status_code == 409
    assert client.post(path(ws) + "/retire", json={"model_id": next_model["id"], "note": "Retire"}).status_code == 200
    assert client.post(path(ws) + "/predict", json={"document_id": corrections[0]["document_id"], "model_id": next_model["id"]}).status_code == 409


def test_small_benchmark_and_leakage_block_promotion(client, monkeypatch):
    ws = workspace(client); configure(monkeypatch)
    doc = upload(client, ws); label = correction(client, ws, doc)
    dataset = freeze(client, ws, [label], "evaluation").json()
    base, candidate = register(client, ws, "base"), register(client, ws, "candidate")
    monkeypatch.setattr(ex, "infer", lambda model, doc: (output(doc), 0.01))
    ev = client.post(path(ws) + "/benchmarks", json={"dataset_id": dataset["id"], "baseline_id": base["id"], "candidate_id": candidate["id"]}).json()
    assert not ev["passed"]
    assert client.post(path(ws) + "/promote", json={"evaluation_id": ev["id"], "expected_version": 0, "note": "No"}).status_code == 409
    configure(monkeypatch, training_groups=["vendor-template-a"])
    leaking = register(client, ws, "candidate")
    assert client.post(path(ws) + "/benchmarks", json={"dataset_id": dataset["id"], "baseline_id": base["id"], "candidate_id": leaking["id"]}).status_code == 409


def test_failed_inference_and_wrong_artifact_are_persisted(client, monkeypatch):
    ws = workspace(client); doc = upload(client, ws); configure(monkeypatch); model = register(client, ws, "candidate")
    monkeypatch.setattr(ex, "infer", lambda *args: (_ for _ in ()).throw(ValueError("bad")))
    result = client.post(path(ws) + "/predict", json={"document_id": doc["id"], "model_id": model["id"]}).json()
    assert result["error"] and result["output"] is None
    assert len(client.get(path(ws)).json()["prediction"]) == 1


def test_score_penalizes_wrong_missing_and_extra_records():
    doc = {"role": "invoice", "pages": [{"text": "A-101 V-1 1200.00 2026-09-01 2026-10-01 USD"}]}
    gold = output(doc)
    predicted = copy.deepcopy(gold); predicted["records"].append(copy.deepcopy(gold["records"][0]))
    # Derived, not written down: the count is however many fields the fixture text
    # actually supplies, so widening the invoice schema does not fail this test for a
    # reason that has nothing to do with scoring.
    present = sum(1 for o in gold["records"][0].values() if o["status"] == "present")
    assert present, "the fixture must extract something for this to measure"

    counts = ex.score(gold, predicted)
    # The duplicate record is entirely false positives; the original is entirely true.
    assert counts["tp"] == present and counts["fp"] == present
    counts = ex.score(gold, None)
    assert counts["fn"] == present and counts["abstained"] == 0


def test_actual_png_ocr_and_pdf_render(client):
    from PIL import Image, ImageDraw, ImageFont
    import pypdfium2 as pdfium
    ws = workspace(client)
    im = Image.new("RGB", (900, 180), "white")
    ImageDraw.Draw(im).text((20, 30), "Invoice A-101 Total 1200.00 USD", fill="black", font=ImageFont.load_default(size=36))
    buffer = io.BytesIO(); im.save(buffer, format="PNG")
    response = client.post(path(ws) + "/documents", files={"file": ("invoice.png", buffer.getvalue(), "image/png")}, data={"role": "invoice"})
    assert response.status_code == 201, response.text
    doc = response.json(); assert doc["pages"][0]["method"] == "ocr"
    assert "1200" in doc["pages"][0]["text"]
    page = client.get(path(ws) + f"/documents/{doc['id']}/pages/1")
    assert page.status_code == 200 and page.content.startswith(b"\x89PNG")
    pdf = pdfium.PdfDocument.new(); pdf.new_page(200, 200); buffer = io.BytesIO(); pdf.save(buffer); pdf.close()
    response = client.post(path(ws) + "/documents", files={"file": ("blank.pdf", buffer.getvalue(), "application/pdf")}, data={"role": "document"})
    assert response.status_code == 201, response.text
    doc = response.json(); assert any("No readable text" in w for w in doc["pages"][0]["warnings"])
    assert client.get(path(ws) + f"/documents/{doc['id']}/pages/1").status_code == 200


@pytest.mark.parametrize("name,content,status", [("bad.exe", b"x", 415), ("empty.txt", b"", 413), ("corrupt.pdf", b"bad-pdf", 422), ("binary.txt", b"\x00bad", 422)])
def test_malformed_documents(client, name, content, status):
    ws = workspace(client)
    response = client.post(path(ws) + "/documents", files={"file": (name, content)}, data={"role": "document"})
    assert response.status_code == status


def test_viewer_cannot_review_and_cross_workspace_denied(client, monkeypatch):
    ws, other = workspace(client), workspace(client)
    monkeypatch.setenv("SCHOOLTRACE_USERS", json.dumps({"viewer": {"password_hash": security.password_hash("pass"), "role": "viewer", "workspaces": [ws]}}))
    assert client.post("/api/access/login", json={"username": "viewer", "password": "pass"}).status_code == 200
    assert client.get(path(ws)).status_code == 200
    assert client.get(path(other)).status_code == 403
    assert client.post(path(ws) + "/models", json={"name": "x", "note": "no"}).status_code == 403


def test_incremental_updates_preserve_previous_records(client):
    ws = reviewed_workspace(client)
    before = client.get(f"/api/workspaces/{ws}/updates").json()
    # What matters is that a later upload *adds* to what is there, not the size of the
    # starting pack, which moves whenever the sample records change.
    assert before["total_records"] > 0
    commit_files(client, ws, [withheld_service_record()])
    after = client.get(f"/api/workspaces/{ws}/updates").json()
    assert after["total_records"] == before["total_records"] + 1
    assert len(after["added_or_revised"]) == 1
    assert not after["rules_scan_current"]
    assert client.post(f"/api/workspaces/{ws}/updates/scan", json={"snapshot_id": before["snapshot_id"]}).status_code == 409
    scanned = client.post(f"/api/workspaces/{ws}/updates/scan", json={"snapshot_id": after["snapshot_id"]})
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["run_id"] is None
    assert client.get(f"/api/workspaces/{ws}/updates").json()["rules_scan_current"]


def test_changed_correction_cannot_commit_old_preview(client):
    ws = workspace(client); doc = upload(client, ws); first = correction(client, ws, doc)
    staged = client.post(path(ws) + "/stage", json={"correction_id": first["id"]}).json()
    batch = ingestion.get_batch(ws, staged["batch_id"])
    correction(client, ws, doc, expected_previous=first["id"])
    response = client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/commit", json={"expected_version": batch["version"], "idempotency_key": "outdated"})
    assert response.status_code == 409 and "stale_extraction" in response.text


def test_document_revision_supersedes_evidence_not_history(client):
    ws = workspace(client); first = upload(client, ws); label = correction(client, ws, first)
    staged = client.post(path(ws) + "/stage", json={"correction_id": label["id"]}).json()
    batch = ingestion.get_batch(ws, staged["batch_id"])
    ingestion.commit(ws, batch["id"], ingestion.CommitRequest(expected_version=batch["version"], idempotency_key="v1"))
    response = client.post(path(ws) + "/documents", files={"file": ("revised.txt", b"Revised A-101 V-1 1200.00 2026-09-01 2026-10-01 USD")}, data={"role": "invoice", "replaces_id": first["id"]})
    assert response.status_code == 201
    second = response.json(); assert second["version"] == 2 and second["lineage_id"] == first["lineage_id"]
    revised = correction(client, ws, second)
    staged = client.post(path(ws) + "/stage", json={"correction_id": revised["id"]}).json()
    batch = ingestion.get_batch(ws, staged["batch_id"])
    ingestion.commit(ws, batch["id"], ingestion.CommitRequest(expected_version=batch["version"], idempotency_key="v2"))
    updates = client.get(f"/api/workspaces/{ws}/updates").json()
    assert updates["total_records"] == 1 and len(updates["superseded"]) == 1
    assert len(client.get(path(ws)).json()["documents"]) == 2
    assert client.get(path(ws) + f"/documents/{first['id']}/original").content.startswith(b"Invoice")
    assert client.post(path(ws) + "/documents", files={"file": ("another.txt", b"Another version")}, data={"role": "invoice", "replaces_id": first["id"]}).status_code == 409


def test_benchmark_job_persistence_and_restart(client, monkeypatch):
    ws = workspace(client); configure(monkeypatch); doc = upload(client, ws)
    data = freeze(client, ws, [correction(client, ws, doc)], "evaluation").json()
    base, candidate = register(client, ws, "base"), register(client, ws, "candidate")
    monkeypatch.setattr(ex, "infer", lambda model, doc: (output(doc), 0.01))
    response = client.post(path(ws) + "/benchmark-jobs", json={"dataset_id": data["id"], "baseline_id": base["id"], "candidate_id": candidate["id"]})
    assert response.status_code == 202
    status = client.get(path(ws)).json()
    assert status["benchmark_job"][0]["status"] == "completed"
    assert status["evaluation"][0]["passed"] is False
    with db.connect() as c:
        ex.put(c, ws, "benchmark_job", {"status": "running"}, "test")
    ex.interrupt_jobs()
    assert client.get(path(ws)).json()["benchmark_job"][-1]["status"] == "interrupted"


@pytest.mark.parametrize("key,value,currency,expected", [
    ("amount", "$1,200.50", "USD", "1200.50"),
    ("amount", "$1,200.50", None, "$1,200.50"),
    ("amount", "1,20.50", "USD", "1,20.50"),
    ("invoice_date", "September 1, 2026", None, "2026-09-01"),
    ("invoice_date", "09/01/26", None, "09/01/26"),
])
def test_conservative_normalization(key, value, currency, expected):
    assert ex.normalize_for_intake(key, value, currency) == expected


def test_artifact_mismatch_and_scope_rejected(client, monkeypatch):
    ws = workspace(client); doc = upload(client, ws); configure(monkeypatch); model = register(client, ws, "candidate")
    import httpx
    original = httpx.Client
    monkeypatch.setattr(ex.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"artifact_sha256": "c" * 64, "output": output(doc)})), **kw))
    result = client.post(path(ws) + "/predict", json={"document_id": doc["id"], "model_id": model["id"]}).json()
    assert result["error"] and result["output"] is None
    configure(monkeypatch, base_revision="changed")
    result = client.post(path(ws) + "/predict", json={"document_id": doc["id"], "model_id": model["id"]}).json()
    assert result["error"]


def test_analyst_cannot_approve_or_export_labels(client, monkeypatch):
    ws = workspace(client); doc = upload(client, ws); reviewed = correction(client, ws, doc)
    data = freeze(client, ws, [reviewed]).json()
    monkeypatch.setenv("SCHOOLTRACE_USERS", json.dumps({"analyst": {"password_hash": security.password_hash("pass"), "role": "analyst", "workspaces": [ws]}}))
    client.post("/api/access/login", json={"username": "analyst", "password": "pass"})
    view = client.get(path(ws)).json()
    assert view["correction"] == [] and "examples" not in view["dataset"][0]
    assert client.get(path(ws) + f"/datasets/{data['id']}/training.jsonl").status_code == 403
    assert client.post(path(ws) + "/stage", json={"correction_id": reviewed["id"]}).status_code == 403


def test_a_live_rescan_is_explicit_and_reuses_a_run_on_the_same_snapshot(client, monkeypatch):
    """A paid rescan happens because someone asked, and only once per snapshot.

    The evidence has not changed between two clicks, so neither would the answer;
    repeating the run would only spend money to reprint it.
    """
    from app import updates
    ws = reviewed_workspace(client)
    snapshot = client.get(f"/api/workspaces/{ws}/updates").json()["snapshot_id"]

    started = []

    async def fake_run(workspace, objective, **kwargs):
        started.append((workspace, objective))
        return {"thread_id": "thread-test", "status": "completed",
                "spend": {"spent_cents": 0, "cap_cents": 1000, "remaining_cents": 1000}}

    import app.graph as graph_module
    monkeypatch.setattr(graph_module, "run_investigation", fake_run)

    first = client.post(f"/api/workspaces/{ws}/updates/scan",
                        json={"snapshot_id": snapshot, "live": True})
    second = client.post(f"/api/workspaces/{ws}/updates/scan",
                         json={"snapshot_id": snapshot, "live": True})

    assert first.status_code == 200, first.text
    assert second.json()["reused"] is True
    assert len(started) == 1, "a second click must not start a second paid run"
    assert snapshot in started[0][1]


def test_a_rules_only_rescan_costs_nothing_and_starts_no_agent(client):
    ws = reviewed_workspace(client)
    snapshot = client.get(f"/api/workspaces/{ws}/updates").json()["snapshot_id"]

    response = client.post(f"/api/workspaces/{ws}/updates/scan",
                           json={"snapshot_id": snapshot, "live": False})

    assert response.status_code == 200
    assert response.json()["run_id"] is None
    assert response.json()["scan_id"]


def test_local_runner_fingerprints_actual_artifacts(tmp_path, monkeypatch):
    from app.extractor_server import bundle_fingerprint
    root = tmp_path / "model"; root.mkdir()
    weights = root / "model.safetensors"; weights.write_bytes(b"synthetic test bytes, not real weights")
    monkeypatch.setenv("EXTRACTOR_MODEL_DIR", str(root))
    monkeypatch.delenv("EXTRACTOR_ADAPTER_DIR", raising=False)
    before = bundle_fingerprint()
    weights.write_bytes(b"different test bytes")
    assert bundle_fingerprint() != before
    (root / "unsafe.bin").write_bytes(b"not allowed")
    with pytest.raises(ValueError, match="pickle"):
        bundle_fingerprint()


def test_local_runner_rejects_browser_and_wrong_identity():
    from app.extractor_server import app as runner
    # No lifespan: no model download/load in an offline regression test.
    runner.state.artifact = "a" * 64
    client = TestClient(runner)
    assert client.post("/extract", headers={"Origin": "http://localhost:3000"}, json={}).status_code == 403
    assert client.post("/extract", headers={"Host": "evil.example"}, json={}).status_code == 403
    assert client.post("/extract", content=b"x" * 1_000_001).status_code == 413
    body = {"schema_version": ex.SCHEMA_VERSION, "artifact_sha256": "b" * 64, "document_type": "invoice",
            "fields": ex.schema("invoice"), "pages": [{"page": 1, "text": "test", "method": "native", "warnings": []}],
            "output_schema": {}, "instruction": "untrusted"}
    assert client.post("/extract", json=body).status_code == 409


def test_each_document_kind_is_staged_under_a_role_an_agent_can_read():
    """A document staged under a role no agent reads is preserved, hashed and
    citable by a person, and invisible to every agent — so extracting it and
    checking its values buys nothing, silently. Everything used to land in
    `document`, which nothing reads.
    """
    from app import roles
    from app.agents.registry import AGENTS
    from app.extraction import EVIDENCE_ROLE

    readable = {role for agent in AGENTS.values() for role in agent.roles}

    for kind, staged_as in EVIDENCE_ROLE.items():
        assert staged_as in roles.DOCUMENT_ROLES, (
            f"{kind!r} stages as {staged_as!r}, which cannot hold a document at all")
        if staged_as == "document":
            continue  # the catch-all; the Document lab says nobody reads it
        readers = sorted(a.id for a in AGENTS.values() if staged_as in a.roles)
        assert readers, f"{kind!r} stages as {staged_as!r}, which no agent reads"


def test_an_invoice_document_reaches_the_agent_whose_charter_covers_it():
    """The mapping is only worth anything if it lands somewhere specific."""
    from app.agents.registry import AGENTS
    from app.extraction import EVIDENCE_ROLE

    assert "invoice" in AGENTS["A1"].roles, "Accounts Payable must read invoice documents"
    assert "invoice" in AGENTS["D1"].roles, "Audit traces a payment to its source document"
    assert EVIDENCE_ROLE["invoice"] == "invoice"
    # And it does not leak to agents whose charter does not cover it.
    assert "invoice" not in AGENTS["C1"].roles, "Budgeting has no business reading invoices"


def test_a_grant_agreement_is_staged_as_the_contract_it_is():
    from app.agents.registry import AGENTS
    from app.extraction import EVIDENCE_ROLE

    assert EVIDENCE_ROLE["grants"] == "contract"
    assert "contract" in AGENTS["B2"].roles, "Accruals reads the terms behind a commitment"


def _invoice(client, ws, number, amount):
    """One checked invoice document, ready to stage."""
    text = (f"Invoice {number} vendor V-1 amount {amount} dated 2026-09-01 "
            "due 2026-10-01 currency USD")
    doc = client.post(path(ws) + "/documents",
                      files={"file": (f"{number}.txt", text.encode(), "text/plain")},
                      data={"role": "invoice"}).json()
    record = {key: {"status": "missing", "value": None, "page": None, "start": None, "end": None}
              for key in ex.schema("invoice")}
    page = doc["pages"][0]["text"]
    for key, value in {"invoice_number": number, "vendor_id": "V-1", "amount": amount,
                       "invoice_date": "2026-09-01", "due_date": "2026-10-01",
                       "currency": "USD"}.items():
        if key in record and value in page:
            start = page.index(value)
            record[key] = {"status": "present", "value": value, "page": 1,
                           "start": start, "end": start + len(value)}
    return client.post(path(ws) + "/corrections", json={
        "document_id": doc["id"], "output": {"schema_version": ex.SCHEMA_VERSION, "records": [record]},
        "group": "vendor-template-a", "training_authorized": True,
        "authorization_note": "Synthetic fixture owned by test",
        "note": "Compared against original", "text_sha256": doc["text_sha256"]}).json()


def test_several_invoices_combine_into_one_register(client):
    """Staging one at a time produced one import per document, so twenty
    invoices meant twenty batches holding a single row each. They belong in one
    spreadsheet a person reviews and commits once."""
    ws = workspace(client)
    corrections = [_invoice(client, ws, "A-101", "1200.00"),
                   _invoice(client, ws, "A-102", "850.00"),
                   _invoice(client, ws, "A-103", "430.00")]

    staged = client.post(path(ws) + "/stage-set", json={
        "correction_ids": [c["id"] for c in corrections], "include_records": True})
    assert staged.status_code == 201, staged.text
    assert staged.json()["combined"] == 3 and staged.json()["rows"] == 3

    batch = ingestion.get_batch(ws, staged.json()["batch_id"])
    csvs = [f for f in batch["files"] if f["name"].endswith(".csv")]
    assert len(csvs) == 1, "three invoices must produce one register, not three"
    assert csvs[0]["row_count"] == 3
    # Every document still contributes its own evidence, because the page
    # citations belong to the PDF they came from.
    assert len([f for f in batch["files"] if f["name"].endswith(".txt")]) == 3


def test_combined_rows_keep_a_distinct_identity_per_document(client):
    """Rows gathered from several documents must not collide on record_id, or
    the register silently holds fewer invoices than were uploaded."""
    ws = workspace(client)
    corrections = [_invoice(client, ws, "A-101", "1200.00"), _invoice(client, ws, "A-102", "850.00")]
    staged = client.post(path(ws) + "/stage-set", json={
        "correction_ids": [c["id"] for c in corrections], "include_records": True}).json()

    batch = ingestion.get_batch(ws, staged["batch_id"])
    register = next(f for f in batch["files"] if f["name"].endswith(".csv"))
    keys = [row["key"] for row in register["preview"]]
    assert len(set(keys)) == len(keys) == 2, keys


def test_a_set_mixing_document_kinds_is_refused(client):
    """Each kind extracts different columns, so one register cannot hold two of
    them without inventing values for the fields the other lacks."""
    ws = workspace(client)
    invoice = _invoice(client, ws, "A-101", "1200.00")
    policy_doc = upload(client, ws, text="Expenses over 500.00 need a second approver.", role="policy")
    policy_correction = correction(client, ws, policy_doc)

    response = client.post(path(ws) + "/stage-set", json={
        "correction_ids": [invoice["id"], policy_correction["id"]], "include_records": True})

    assert response.status_code == 422
    assert "one kind of document at a time" in response.json()["detail"]


def test_a_superseded_correction_cannot_be_combined(client):
    """The same guard the single path applies: values nobody checked against
    the text they now describe must not reach an import."""
    ws = workspace(client)
    first = _invoice(client, ws, "A-101", "1200.00")
    doc_id = first["document_id"]
    current = next(d for d in client.get(path(ws)).json()["documents"] if d["id"] == doc_id)
    client.post(path(ws) + f"/documents/{doc_id}/transcription", json={
        "expected_text_sha256": current["text_sha256"],
        "pages": ["Invoice A-101 vendor V-1 amount 9999.00 dated 2026-09-01"],
        "note": "Re-read the original"})

    response = client.post(path(ws) + "/stage-set", json={
        "correction_ids": [first["id"]], "include_records": True})

    assert response.status_code == 409
