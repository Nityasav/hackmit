"""Recovering structured records from files that were saved as plain documents.

Ported across the SaaS rework. The detector itself needed no change — it was written
against `roles.FIELDS` rather than against a list of role names, so it recognizes the
new vocabulary for free. These tests are retargeted to that vocabulary and to what the
detector must refuse.
"""

from __future__ import annotations

from tests.conftest import SAMPLE_FILES, sample
from tests.test_ingestion import client, commit, create, upload  # noqa: F401  (fixtures)


#: Structured roles from the pack, uploaded as plain documents so there is something
#: to recover. The policy and the withheld note are genuinely documents and stay so.
RECOVERABLE = ["chart", "opening", "ledger", "vendors", "vendor_invoices"]


def test_auto_detection_updates_requirements_only_after_commit(client):
    ws = create(client)
    files = [{**sample(role), "role": "document", "options": {"auto_detect": True}} for role in RECOVERABLE]
    batch = upload(client, ws, files)
    assert [f["options"]["role"] for f in batch["files"]] == RECOVERABLE
    base = f"/api/workspaces/{ws}/coverage"
    before = client.get(base).json()
    assert before["counts"]["vendors"] == 0
    commit(client, ws, batch)
    after = client.get(base).json()
    assert after["counts"]["vendors"] > 0
    assert next(r for r in after["requirements"] if r["role"] == "vendors")["satisfied"]


def _as_documents(roles: list[str]) -> list[dict]:
    return [{**sample(role), "role": "document"} for role in roles]


def test_saved_csv_recovery_validates_and_is_repeat_safe(client):
    ws = create(client)
    files = _as_documents(RECOVERABLE)
    original = upload(client, ws, files)
    commit(client, ws, original)
    base = f"/api/workspaces/{ws}"

    assert client.get(base + "/coverage").json()["counts"]["ledger"] == 0

    response = client.post(base + "/sources/detect")
    assert response.status_code == 200, response.text
    result = response.json()

    assert result["detected"] == len(RECOVERABLE)
    assert result["batch"]["status"] == "ready_to_commit", result["batch"]["issues"]
    # Detection stages a normal import; it does not manufacture coverage on its own.
    assert client.get(base + "/coverage").json()["counts"]["ledger"] == 0

    commit(client, ws, result["batch"])
    coverage = client.get(base + "/coverage").json()
    assert coverage["counts"]["ledger"] == 8
    assert coverage["counts"]["vendor_invoices"] == 2

    # Running it again finds nothing: the same bytes are already represented.
    assert client.post(base + "/sources/detect").json()["batch"] is None

    # The original upload is still byte-identical, whatever was derived from it.
    saved = client.get(base + f"/sources/{original['files'][0]['id']}/download")
    assert saved.content == files[0]["content"].encode()


def test_a_document_that_is_really_a_document_is_left_alone(client):
    """Only a complete schema match is recovered. Prose stays evidence."""
    ws = create(client)
    policy = sample("policy")
    commit(client, ws, upload(client, ws, [policy]))

    result = client.post(f"/api/workspaces/{ws}/sources/detect").json()

    assert result["detected"] == 0 and result["batch"] is None


def test_a_csv_matching_no_role_is_not_guessed_at(client):
    ws = create(client)
    mystery = {"name": "mystery.csv", "role": "document",
               "content": "alpha,beta,gamma\n1,2,3\n"}
    commit(client, ws, upload(client, ws, [mystery]))

    result = client.post(f"/api/workspaces/{ws}/sources/detect").json()

    assert result["detected"] == 0, "a file matching no schema must stay a document"


def test_invalid_saved_rows_still_require_review(client):
    """Recovery runs the normal validators; it is not a way around them."""
    ws = create(client)
    chart = sample("chart")
    broken = {"name": "ledger.csv", "role": "document",
              "content": sample("ledger")["content"].replace("6100,1200.00", "6100,1201.00")}
    commit(client, ws, upload(client, ws, [chart, broken]))

    result = client.post(f"/api/workspaces/{ws}/sources/detect").json()

    # The chart went in under its own role, so only the ledger is recovered.
    assert result["detected"] == 1
    assert result["batch"]["status"] != "ready_to_commit"
    assert "unbalanced_journal" in {i["code"] for i in result["batch"]["issues"]}
