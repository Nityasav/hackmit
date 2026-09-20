"""Offline import and specialist-tool smoke test; never uses the user's database.

Run with api/.venv/bin/python fixtures/validate_saas_pack.py PATH_TO_PERIOD.
Outputs JSON to stdout. No model calls or synthetic decisions are created.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

SETTINGS = {"home_jurisdiction": "US-CA", "fiscal_year_end": "12-31",
            "materiality_cents": 100000, "approval_limit_cents": 500000,
            "close_target_day": 5}


def validate(path):
    from fastapi.testclient import TestClient
    from app.main import app
    from app import ingestion
    from app.agents.registry import AGENTS
    from app.agents.tools import Toolbox, dispatch
    from app.agents.budget import Meter
    with tempfile.TemporaryDirectory(prefix="sherlock-pack-check-") as temp:
        old = os.environ.get("SCHOOLTRACE_DATA_DIR")
        os.environ["SCHOOLTRACE_DATA_DIR"] = temp
        try:
            with TestClient(app, headers={"X-SchoolTrace-Reviewer": "local-reviewer"}) as client:
                response = client.post("/api/workspaces", json={"name": "Synthetic pack validation",
                    "start": "2026-09-01", "end": "2026-09-30", "scope": "Offline tool testing",
                    "settings": SETTINGS})
                assert response.status_code == 201, response.text
                ws = response.json()["id"]
                files = sorted(path.glob("*.csv"))
                meta = [{"role": "document", "auto_detect": True} for p in files]
                response = client.post(f"/api/workspaces/{ws}/imports",
                    files=[("files", (p.name, p.read_bytes(), "text/plain")) for p in files],
                    data={"metadata": json.dumps(meta)})
                assert response.status_code == 201, response.text
                batch = response.json()
                assert batch["status"] == "ready_to_commit", batch["issues"]
                response = client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/commit",
                    json={"expected_version": batch["version"], "idempotency_key": batch["id"]})
                assert response.status_code == 200, response.text
                coverage = client.get(f"/api/workspaces/{ws}/coverage").json()
                missing = [r["id"] for r in coverage["requirements"] if not r["satisfied"]]
                assert all(r["kind"] == "document" for r in coverage["requirements"] if not r["satisfied"]), missing
                data = ingestion.financial_records(ws)
                config = ingestion.workspace_config(ws)
                invoice = next(r["record_key"] for r in data["records"] if r["role"] == "vendor_invoices")
                results = {}
                shared = {"read_records", "read_source", "read_event", "delegate", "check_precedents"}
                for spec in AGENTS.values():
                    if spec.tier != "subagent":
                        continue
                    box = Toolbox(ws, spec, Meter(), data["records"], config, "fixture", "offline")
                    results[spec.id] = {}
                    for tool in spec.tools:
                        if tool in shared:
                            continue
                        args = {"invoice_key": invoice} if tool in {"three_way_match", "check_policy", "trace_transaction"} else {}
                        results[spec.id][tool] = dispatch(box, tool, args)
                    assert results[spec.id], f"No substantive tool tested for {spec.id}"
                return {"mode": "offline deterministic tools, not live model evaluation",
                        "records": len(data["records"]), "requirements_supplied": len(coverage["requirements"]) - len(missing),
                        "document_requirements_not_supplied_by_csv": missing,
                        "specialists_tested": len(results), "results": results}
        finally:
            if old is None:
                os.environ.pop("SCHOOLTRACE_DATA_DIR", None)
            else:
                os.environ["SCHOOLTRACE_DATA_DIR"] = old


if __name__ == "__main__":
    result = validate(Path(sys.argv[1]))
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k != "results"}))
    else:
        print(json.dumps(result, indent=2))
