from tests.test_ingestion import client, create, upload, commit
from tests.conftest import SAMPLE_FILES


def test_saved_csv_recovery_validates_and_is_repeat_safe(client):
    ws = create(client)
    files = [{**f, "role": "document"} for f in SAMPLE_FILES[:5]]
    original = upload(client, ws, files)
    commit(client, ws, original)
    base = f"/api/workspaces/{ws}"
    assert client.get(base + "/coverage").json()["counts"]["ledger"] == 0
    response = client.post(base + "/sources/detect")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["detected"] == 5
    assert result["batch"]["status"] == "ready_to_commit"
    # Detection alone does not manufacture coverage.
    assert client.get(base + "/coverage").json()["counts"]["ledger"] == 0
    commit(client, ws, result["batch"])
    coverage = client.get(base + "/coverage").json()
    assert coverage["counts"]["ledger"] == 2
    assert coverage["counts"]["payroll"] == 1
    assert coverage["counts"]["policy"] == 0
    assert client.post(base + "/sources/detect").json()["batch"] is None
    assert client.get(base + f"/sources/{original['files'][0]['id']}/download").content == files[0]["content"].encode()


def test_invalid_saved_rows_still_require_review(client):
    ws = create(client)
    file = {**SAMPLE_FILES[0], "role": "document"}
    file["content"] = file["content"].replace("asset", "nonsense")
    commit(client, ws, upload(client, ws, [file]))
    result = client.post(f"/api/workspaces/{ws}/sources/detect").json()
    assert result["batch"]["status"] != "ready_to_commit"
    commit(client, ws, result["batch"], expected=409)


def test_unknown_csv_is_not_guessed_from_name(client):
    ws = create(client)
    commit(client, ws, upload(client, ws, [{"name": "payroll.csv", "role": "document", "content": "note,value\nPayroll,42\n"}]))
    assert client.post(f"/api/workspaces/{ws}/sources/detect").json()["batch"] is None


def test_public_workspace_keeps_reference_evidence(client):
    ws = create(client, kind="public", currency="CAD")
    commit(client, ws, upload(client, ws, [{**SAMPLE_FILES[0], "role": "document"}]))
    assert client.post(f"/api/workspaces/{ws}/sources/detect").json()["batch"] is None
