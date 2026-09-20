from tests.test_ingestion import client, create, upload, commit


def test_coverage_results_are_calculated_cited_and_snapshot_bound(client):
    ws = create(client)
    base = f"/api/workspaces/{ws}"
    commit(client, ws, upload(client, ws))
    def cards():
        return {c["id"]: c for c in client.get(base + "/coverage").json()["capabilities"]}
    assert cards()["management_statements"]["status"] == "ready_to_check"
    scan = client.post(base + "/review/scans")
    assert scan.status_code == 201
    management = cards()["management_statements"]
    assert management["status"] == "checks_passed"
    results = {r["id"]: r for r in management["results"]}
    assert results["management-trial-balance"]["amount_cents"] == 0
    assert results["management-account-1000"]["amount_cents"] == 1000000
    assert results["management-period-result"]["amount_cents"] == -1000000
    assert results["management-period-result"]["evidence"]
    assert cards()["payroll_allocation_confirmation"]["status"] == "evidence_gaps"
    commit(client, ws, upload(client, ws, [{"name": "later.txt", "role": "document", "content": "New supporting note"}]))
    assert cards()["management_statements"]["results"] == []
    assert cards()["management_statements"]["status"] == "ready_to_check"


def test_public_checks_remain_unsupported(client):
    ws = create(client, kind="public", currency="CAD")
    commit(client, ws, upload(client, ws, [{"name": "report.txt", "role": "document", "content": "Public report"}]))
    coverage = client.get(f"/api/workspaces/{ws}/coverage").json()
    assert all(not c["runnable"] for c in coverage["capabilities"])
    assert client.post(f"/api/workspaces/{ws}/review/scans").status_code == 409
