"""Connected ports, independent provenance, lifecycle and optional provider smoke."""
import asyncio
import os

import pytest

from app.agents.model import StructuredSpecialistModel
from app.agents.payroll import DraftClaim, DraftFindings, EvidenceSelection
from app.agents.team import SnapshotAuditor, SnapshotSpecialist
from app.cfo.demo import DemoData, ScriptedCFO
from app.cfo.engine import CFOEngine
from app.cfo.repository import RunRepository
from app.cfo.schemas import Claim, Limits, Review, Run, RunRequest, TaskSpec, TaskState
from app.cfo.tools import EvidenceTools


class FakeModel:
    instances = []
    verdict = "accept"

    def __init__(self):
        self.closed = False
        self.__class__.instances.append(self)

    def reset(self):
        pass

    async def generate(self, system, instruction, payload, schema):
        if schema is EvidenceSelection:
            return EvidenceSelection(focus="Read originals", source_ids=[s["id"] for s in payload["sources"]], calculation_ids=[])
        if schema is DraftFindings:
            task_id = payload["task"]["id"]
            return DraftFindings(summary="Read the delegated evidence.", evidence_requests=[], claims=[DraftClaim(
                id=task_id + "-claim", event_key=task_id, title="Evidence observation",
                conclusion="The source describes allocation support.", disposition="explained",
                evidence_ids=[e["source_id"] for e in payload["evidence"]], calculation_id=None,
                proposed_action="Proposed human review of the source.")])
        assert schema is Review and payload["evidence"]
        return Review(verdict=self.verdict, rationale="Checked originals.", required_action="Provide additional support.")

    async def close(self):
        self.closed = True


@pytest.fixture
def models(monkeypatch):
    FakeModel.instances = []
    FakeModel.verdict = "accept"
    monkeypatch.setattr(StructuredSpecialistModel, "from_env", lambda **kwargs: FakeModel())
    return FakeModel


def test_all_five_roles_connected_and_clients_closed(tmp_path, models):
    engine = CFOEngine(DemoData(), {r: SnapshotSpecialist(r) for r in ("ap", "py", "gr")},
                       SnapshotAuditor(), ScriptedCFO(), RunRepository(tmp_path / "runs.db"))
    run = asyncio.run(engine.execute(engine.create(RunRequest(workflow="five_agent"))))
    assert run.status == "completed", run.unresolved
    assert {t.spec.role for t in run.tasks} == {"ap", "py", "gr"}
    assert len(run.accepted) == 3
    assert {e.actor for e in run.events} == {"cfo", "ap", "py", "gr", "au"}
    for accepted in run.accepted:
        fresh = {ref for e in run.events if e.actor == "au" and e.task_id == accepted.task_id
                 and e.action == "read_source.completed" for ref in e.references}
        assert set(accepted.claim.evidence_ids) <= fresh
    assert len(models.instances) == 6
    assert all(m.closed for m in models.instances)


def test_auditor_rejection_never_enters_report(tmp_path, models):
    models.verdict = "needs_evidence"
    engine = CFOEngine(DemoData(), {r: SnapshotSpecialist(r) for r in ("ap", "py", "gr")},
                       SnapshotAuditor(), ScriptedCFO(), RunRepository(tmp_path / "runs.db"))
    run = asyncio.run(engine.execute(engine.create(RunRequest(workflow="five_agent"))))
    assert run.status in {"partial", "needs_evidence"}
    assert not run.accepted and run.unresolved
    assert all(m.closed for m in models.instances)


def test_coverage_cannot_exceed_task_budget(tmp_path, models):
    engine = CFOEngine(DemoData(), {r: SnapshotSpecialist(r) for r in ("ap", "py", "gr")},
                       SnapshotAuditor(), ScriptedCFO(), RunRepository(tmp_path / "runs.db"))
    run = asyncio.run(engine.execute(engine.create(RunRequest(workflow="five_agent", limits=Limits(max_tasks=2)))))
    assert run.status == "failed" and not run.accepted
    assert not models.instances


def test_auditor_reperforms_engine_calculation(models):
    async def exercise():
        data = DemoData()
        scope = await data.snapshot("sandbox")
        run = Run(id="review", request=RunRequest())
        task = TaskState(spec=TaskSpec(id="allocation", role="py", objective="Check", success_criteria="Evidence",
                                      source_ids=[s.id for s in scope.sources]))
        tools = EvidenceTools(data, scope, run, task, "au", lambda *args: None, task.spec.source_ids)
        claim = Claim(id="claim", event_key="event", title="Allocation", conclusion="Needs correction",
                      disposition="substantiated", evidence_ids=task.spec.source_ids, calculation_id="payroll-allocation")
        review = await SnapshotAuditor().review(claim, scope, tools)
        assert review.verdict == "accept"
        assert tools.validate_claim(claim).amount_cents == 400000
        assert run.tool_calls == 4
    asyncio.run(exercise())


def test_model_client_closed_after_provider_failure(monkeypatch):
    model = FakeModel()
    async def fail(*args, **kwargs):
        raise RuntimeError("Provider unavailable")
    model.generate = fail
    monkeypatch.setattr(StructuredSpecialistModel, "from_env", lambda **kwargs: model)
    async def exercise():
        data = DemoData()
        scope = await data.snapshot("sandbox")
        task = TaskSpec(id="task", role="ap", objective="Check", success_criteria="Evidence", source_ids=["award"])
        run = Run(id="failure", request=RunRequest())
        tools = EvidenceTools(data, scope, run, TaskState(spec=task), "ap", lambda *args: None, task.source_ids)
        with pytest.raises(RuntimeError):
            await SnapshotSpecialist("ap").investigate(task, scope, tools, [], None)
    asyncio.run(exercise())
    assert model.closed


def test_truncated_original_is_not_accepted(models):
    class TruncatedData(DemoData):
        async def read_source(self, scope, source_id):
            span = await super().read_source(scope, source_id)
            span.text += "[Truncated for review; request a narrower excerpt for the remainder.]"
            return span
    async def exercise():
        data = TruncatedData()
        scope = await data.snapshot("sandbox")
        task = TaskState(spec=TaskSpec(id="task", role="gr", objective="Check", success_criteria="Evidence", source_ids=["award"]))
        tools = EvidenceTools(data, scope, Run(id="truncated", request=RunRequest()), task, "au", lambda *args: None, ["award"])
        claim = Claim(id="claim", event_key="event", title="Terms", conclusion="Terms supported", disposition="explained", evidence_ids=["award"])
        review = await SnapshotAuditor().review(claim, scope, tools)
        assert review.verdict == "needs_evidence"
        assert not models.instances
    asyncio.run(exercise())


def test_api_default_factory_runs_committed_workspace(tmp_path, monkeypatch, models):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.cfo.model import StructuredCFOModel
    from app.cfo.schemas import Plan
    from tests.test_cfo_intake import commit_pack, HEADERS

    class Planner(ScriptedCFO):
        async def plan(self, objective, scope):
            return Plan(rationale="Independent scoped tasks", tasks=[TaskSpec(
                id=role, role=role, objective="Review source evidence", success_criteria="Cited observations",
                source_ids=[s.id for s in scope.sources][:2]) for role in ("ap", "py", "gr")])

    monkeypatch.delattr(app.state, "cfo_runtime", raising=False)
    monkeypatch.delenv("CFO_ADAPTER_FACTORY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-sent")
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path / "intake"))
    monkeypatch.setattr(StructuredCFOModel, "from_env", lambda: Planner())
    with TestClient(app, headers=HEADERS) as client:
        workspace = commit_pack(client, later=True)
        response = client.post("/api/cfo/runs", json={"workspace": workspace, "mode": "live", "workflow": "five_agent"})
        assert response.status_code == 202, response.text
        async def finish():
            await asyncio.gather(*list(app.state.cfo_runtime.pending.values()))
        client.portal.call(finish)
        run = client.get("/api/cfo/runs/" + response.json()["id"]).json()
        assert run["status"] in {"completed", "needs_evidence"}
        assert len(run["accepted"]) == 3
        assert run["scope"]["workspace"] == workspace
        assert all(e["actor"] != "scripted" for e in run["events"])
        assert client.get("/api/cfo/runs/" + run["id"] + "/report").status_code == 200


@pytest.mark.skipif(os.getenv("RUN_FIVE_AGENT_LIVE") != "1", reason="Explicit opt-in paid synthetic provider smoke")
def test_live_five_agent_snapshot(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.cfo.model import StructuredCFOModel
    from app.integrations.cfo_factory import create_adapters
    from tests.test_cfo_intake import commit_pack, HEADERS

    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path / "intake"))
    monkeypatch.setenv("CFO_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("SPECIALIST_MODEL", "gpt-5.4-mini")
    with TestClient(app, headers=HEADERS) as client:
        workspace = commit_pack(client, later=True)

    async def exercise():
        adapters = create_adapters()
        model = StructuredCFOModel.from_env()
        try:
            engine = CFOEngine(adapters.data, adapters.specialists, adapters.auditor, model,
                               RunRepository(tmp_path / "runs.db"))
            run = await engine.execute(engine.create(RunRequest(workspace=workspace, mode="live", workflow="five_agent",
                objective="Review the committed fictional records. Use one independent task per specialist. Return at most one narrow supported claim per task plus evidence gaps; do not claim AP is clear without invoices.",
                limits=Limits(call_timeout_s=180))))
            assert run.status in {"completed", "needs_evidence"}, run.unresolved
            assert {t.spec.role for t in run.tasks} == {"ap", "py", "gr"}
            assert all(t.attempts for t in run.tasks)
            assert any(e.actor == "au" and e.action.startswith("review.") for e in run.events)
            assert run.report_markdown
            print(f"LIVE: status={run.status} tasks={len(run.tasks)} accepted={len(run.accepted)} evidence_calls={run.tool_calls} CFO_calls={run.model_calls}")
        finally:
            await model.close()
    asyncio.run(exercise())
