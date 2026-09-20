"""The CFO data bridge over committed intake snapshots.

These check the boundary only: what the coordinator may read, and when it must
refuse. They do not exercise specialist reasoning, which is a separate track.
"""
import asyncio
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.agents.team import SnapshotSpecialist, SnapshotAuditor
from app.cfo.api import CFORuntime
from app.cfo.repository import RunRepository
from app.cfo.schemas import RunRequest
from app.integrations.cfo_factory import create_adapters
from app.integrations.cfo_intake import IntakeDataSource
from app.main import app

SAMPLE = json.loads((Path(__file__).resolve().parents[2] / "contracts/fixtures/intake.json").read_text(encoding="utf-8"))
HEADERS = {"X-SchoolTrace-Reviewer": "local-reviewer"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    with TestClient(app, headers=HEADERS) as c:
        yield c


def commit_pack(client, later=False):
    """Create a workspace and commit the fixture pack; `later` adds the service record."""
    ws = client.post("/api/workspaces", json={"name": "Fictional school", "start": "2026-09-01",
                                              "end": "2026-09-30", "scope": "September close"}).json()["id"]
    files = [f for f in SAMPLE["files"] if later or not f.get("later")]
    batch = client.post(f"/api/workspaces/{ws}/imports",
                        files=[("files", (f["name"], f["content"].encode(), "text/plain")) for f in files],
                        data={"metadata": json.dumps([{"role": f["role"], **f.get("options", {})} for f in files])}).json()
    saved = client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/commit",
                        json={"expected_version": batch["version"], "idempotency_key": batch["id"]})
    assert saved.status_code == 200, saved.text
    return ws


def test_snapshot_maps_committed_sources_domains_and_gaps(client):
    ws = commit_pack(client)
    scope = asyncio.run(IntakeDataSource().snapshot(ws))
    assert scope.workspace == ws and scope.snapshot_id
    assert scope.institution == "Fictional school"
    assert scope.period == "2026-09-01 to 2026-09-30"
    assert scope.accounting_profile == "DEMO_US_DISTRICT_MANAGEMENT_ACCRUAL_V1"
    domains = {s.title: s.domain for s in scope.sources}
    assert domains["payroll.csv"] == "py" and domains["grants.csv"] == "gr"
    assert domains["ledger.csv"] == "shared"
    # Document evidence is a first-class source, not just ledger CSVs.
    assert domains["award-terms.md"] == "shared"
    assert any("missing service" in gap for gap in scope.gaps)
    # Amounts come from the accounting engine, per domain that has records to work on.
    published = {c.id for c in scope.calculations}
    assert "payroll-gross-to-net" in published and "payroll-award-ceiling-excess" in published
    # The pack charges an award through payroll, so the award-level tests publish too.
    assert "grants-combined-ceiling-excess" in published
    # It commits no invoices, so AP can cite evidence but still cannot assert an amount.
    assert not any(c.id.startswith("ap-") for c in scope.calculations)
    assert any("ap amounts cannot be confirmed" in gap for gap in scope.gaps)
    # Each published calculation names sources the specialist can actually read.
    available = {s.id for s in scope.sources}
    assert all(set(c.source_ids) <= available and c.source_ids for c in scope.calculations)


def test_read_source_returns_original_text_bound_to_the_snapshot(client):
    ws = commit_pack(client)
    data = IntakeDataSource()
    scope = asyncio.run(data.snapshot(ws))
    terms = next(s for s in scope.sources if s.title == "award-terms.md")
    span = asyncio.run(data.read_source(scope, terms.id))
    assert span.id == terms.id and span.snapshot_id == scope.snapshot_id
    assert "Fictional Student Support Award" in span.text
    assert "award-terms.md lines 1-" in span.locator


def test_unknown_source_is_refused(client):
    ws = commit_pack(client)
    data = IntakeDataSource()
    scope = asyncio.run(data.snapshot(ws))
    with pytest.raises(ValueError, match="not part of the current committed snapshot"):
        asyncio.run(data.read_source(scope, "source-does-not-exist"))


def test_new_evidence_supersedes_the_snapshot_and_blocks_stale_reads(client):
    ws = commit_pack(client)
    data = IntakeDataSource()
    scope = asyncio.run(data.snapshot(ws))
    source_id = scope.sources[0].id
    # Supplying the withheld service record publishes a new snapshot.
    later = next(f for f in SAMPLE["files"] if f.get("later"))
    batch = client.post(f"/api/workspaces/{ws}/imports",
                        files=[("files", (later["name"], later["content"].encode(), "text/plain"))],
                        data={"metadata": json.dumps([{"role": later["role"]}])}).json()
    client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/commit",
                json={"expected_version": batch["version"], "idempotency_key": batch["id"]})
    refreshed = asyncio.run(data.snapshot(ws))
    assert any(s.title == "service-record.md" for s in refreshed.sources)
    assert refreshed.snapshot_id != scope.snapshot_id
    assert not any("missing service" in gap for gap in refreshed.gaps)
    # Evidence from the superseded snapshot must not reach a run planned against it.
    with pytest.raises(ValueError, match="snapshot changed"):
        asyncio.run(data.read_source(scope, source_id))


def test_calculate_fails_closed_for_identifiers_the_engine_does_not_publish(client):
    ws = commit_pack(client)
    data = IntakeDataSource()
    scope = asyncio.run(data.snapshot(ws))
    # An AP or grant amount has no engine behind it yet, and is refused rather than guessed.
    with pytest.raises(ValueError, match="No deterministic calculation"):
        asyncio.run(data.calculate(scope, "invoice-duplicate-exposure"))


def test_published_payroll_amounts_are_bound_to_their_snapshot_and_sources(client):
    ws = commit_pack(client)
    data = IntakeDataSource()
    scope = asyncio.run(data.snapshot(ws))
    result = asyncio.run(data.calculate(scope, "payroll-unsupported-by-service-evidence"))
    assert result.snapshot_id == scope.snapshot_id
    # The fixture charges the whole salary to the award with no service record committed.
    assert result.amount_cents == 1_000_000
    assert result.category == "reclassification" and result.cash_delta_cents == 0
    assert set(result.source_ids) <= {s.id for s in scope.sources}
    spec = next(c for c in scope.calculations if c.id == result.id)
    assert set(result.source_ids) == set(spec.source_ids)


def test_committing_service_evidence_changes_the_amount_the_engine_publishes(client):
    ws = commit_pack(client, later=True)
    data = IntakeDataSource()
    scope = asyncio.run(data.snapshot(ws))
    result = asyncio.run(data.calculate(scope, "payroll-unsupported-by-service-evidence"))
    # A service record exists, so the engine no longer asserts the whole allocation is unsupported.
    assert result.amount_cents == 0 and result.category == "none"
    # It also refuses to read the split out of the document's prose.
    assert "does not judge" in result.description


def test_amounts_from_a_superseded_snapshot_are_refused(client):
    ws = commit_pack(client)
    data = IntakeDataSource()
    scope = asyncio.run(data.snapshot(ws))
    later = next(f for f in SAMPLE["files"] if f.get("later"))
    batch = client.post(f"/api/workspaces/{ws}/imports",
                        files=[("files", (later["name"], later["content"].encode(), "text/plain"))],
                        data={"metadata": json.dumps([{"role": later["role"]}])}).json()
    client.post(f"/api/workspaces/{ws}/imports/{batch['id']}/commit",
                json={"expected_version": batch["version"], "idempotency_key": batch["id"]})
    with pytest.raises(ValueError, match="snapshot changed"):
        asyncio.run(data.calculate(scope, "payroll-unsupported-by-service-evidence"))


def test_workspace_without_a_committed_snapshot_is_refused(client):
    ws = client.post("/api/workspaces", json={"name": "Empty", "start": "2026-09-01",
                                              "end": "2026-09-30", "scope": "Nothing yet"}).json()["id"]
    with pytest.raises(ValueError, match="no committed snapshot"):
        asyncio.run(IntakeDataSource().snapshot(ws))
    with pytest.raises(ValueError, match="unavailable|Unknown"):
        asyncio.run(IntakeDataSource().snapshot("ws-nonexistent"))


def unconfigure_specialist_model(monkeypatch):
    for name in ["SPECIALIST_PROVIDER", "SPECIALIST_MODEL", "CFO_PROVIDER", "CFO_MODEL", "OPENAI_API_KEY"]:
        monkeypatch.delenv(name, raising=False)


def test_factory_omits_the_payroll_agent_when_no_specialist_model_is_configured(tmp_path, monkeypatch):
    unconfigure_specialist_model(monkeypatch)
    adapters = create_adapters()
    assert isinstance(adapters.data, IntakeDataSource)
    assert adapters.specialists == {} and adapters.auditor is None
    runtime = CFORuntime(RunRepository(tmp_path / "runs.sqlite3"), adapters)
    with pytest.raises(HTTPException) as error:
        runtime.start(RunRequest(workspace="ws-abc123", mode="live"))
    assert error.value.status_code == 503
    assert "agents are not" in error.value.detail


def test_factory_registers_all_snapshot_agents(tmp_path, monkeypatch):
    monkeypatch.setenv("SPECIALIST_PROVIDER", "openai")
    monkeypatch.setenv("SPECIALIST_MODEL", "test-model-id")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    adapters = create_adapters()
    assert set(adapters.specialists) == {"ap", "py", "gr"}
    assert all(isinstance(agent, SnapshotSpecialist) for agent in adapters.specialists.values())
    assert isinstance(adapters.auditor, SnapshotAuditor)


def test_intake_workspace_ids_are_accepted_but_never_served_by_the_scripted_harness(tmp_path):
    assert RunRequest(workspace="ws-0123456789abcdef").workspace == "ws-0123456789abcdef"
    runtime = CFORuntime(RunRepository(tmp_path / "runs.sqlite3"))
    with pytest.raises(HTTPException) as error:
        runtime.start(RunRequest(workspace="ws-0123456789abcdef", mode="scripted"))
    assert error.value.status_code == 422
