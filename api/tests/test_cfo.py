import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.cfo.api import Adapters, CFORuntime
from app.cfo.engine import CFOEngine
from app.cfo.model import StructuredCFOModel
from app.cfo.repository import RunRepository
from app.cfo.schemas import FollowUp, Limits, Narrative, NarrativeItem, Plan, Review, RunRequest, TaskSpec
from tests.conftest import FixtureData, StubAuditor, StubPlanner, StubSpecialist


def execute(tmp_path, *, data=None, model=None, worker=None, auditor=None, limits=None):
    repo = RunRepository(tmp_path / "runs.sqlite3")
    engine = CFOEngine(data or FixtureData(), {r: worker or StubSpecialist() for r in ["ap", "py", "gr"]},
                       auditor or StubAuditor(), model or StubPlanner(), repo)
    run = engine.create(RunRequest(limits=limits or Limits()))
    result = asyncio.run(engine.execute(run))
    assert repo.get(run.id) == result
    return result


@pytest.mark.parametrize("share,cents", [(60, 400_000), (80, 200_000)])
def test_calculations_are_data_driven_and_persisted(tmp_path, share, cents):
    run = execute(tmp_path, data=FixtureData(share))
    assert run.status == "completed"
    calc = next(a.calculation for a in run.accepted if a.calculation)
    assert calc.amount_cents == cents
    assert calc.cash_delta_cents == 0
    assert run.tool_calls == 10
    assert "No financial changes have been approved or applied" in run.briefing
    assert not hasattr(run, "approvals")


def test_missing_evidence_never_becomes_confirmed_error(tmp_path):
    run = execute(tmp_path, data=FixtureData(missing_service=True))
    assert run.status == "needs_evidence"
    assert all(a.claim.id != "payroll-reclass" for a in run.accepted)
    assert "current payroll service record" in run.report_markdown
    assert "$4,000" not in run.report_markdown


class BadPlan(StubPlanner):
    def __init__(self, case):
        self.case = case

    async def plan(self, objective, scope):
        plan = await super().plan(objective, scope)
        if self.case == "cycle":
            plan.tasks[0].depends_on = ["allocation"]
        elif self.case == "source":
            plan.tasks[0].source_ids.append("private-other-school")
        elif self.case == "duplicate":
            plan.tasks[1].id = plan.tasks[0].id
        else:
            plan.tasks[0].depends_on = ["nonexistent"]
        return plan


@pytest.mark.parametrize("case", ["cycle", "source", "duplicate", "dependency"])
def test_invalid_plans_never_dispatch_workers(tmp_path, case):
    run = execute(tmp_path, model=BadPlan(case))
    assert run.status == "failed"
    assert run.tool_calls == 0
    assert not any(e.action == "delegate" for e in run.events)


class RubberStamp:
    async def review(self, claim, scope, tools):
        return Review(verdict="accept", rationale="I trust the specialist.")


def test_auditor_must_retrieve_sources_independently(tmp_path):
    run = execute(tmp_path, auditor=RubberStamp())
    assert run.status == "partial"
    assert not run.accepted
    assert run.tasks[1].status == "blocked"


class SkipCalculation(StubAuditor):
    async def review(self, claim, scope, tools):
        for source in claim.evidence_ids:
            await tools.read_source(source)
        return Review(verdict="accept", rationale="Sources retrieved but calculation skipped.")


def test_auditor_must_reperform_calculation(tmp_path):
    run = execute(tmp_path, auditor=SkipCalculation())
    assert run.status == "partial"
    assert not any(a.calculation for a in run.accepted)


class RejectOnce(StubAuditor):
    def __init__(self):
        self.seen = set()

    async def review(self, claim, scope, tools):
        if claim.id not in self.seen:
            self.seen.add(claim.id)
            return Review(verdict="reject", rationale="Please narrow the conclusion.", required_action="Restate the claim within the cited evidence scope.")
        return await super().review(claim, scope, tools)


def test_reviewer_challenge_triggers_bounded_cfo_followup(tmp_path):
    run = execute(tmp_path, auditor=RejectOnce())
    assert run.status == "completed"
    assert all(t.attempts == 2 for t in run.tasks)
    assert sum(e.action == "follow_up.completed" for e in run.events) == 2


class RejectAlways:
    async def review(self, claim, scope, tools):
        return Review(verdict="reject", rationale="Unsupported conclusion.", required_action="Find independent corroboration.")


def test_review_exhaustion_preserves_unresolved_claim(tmp_path):
    run = execute(tmp_path, auditor=RejectAlways())
    assert run.tasks[0].attempts == 2
    assert not run.accepted
    assert "Unsupported conclusion" in run.report_markdown
    assert run.status != "completed"


def test_tool_budget_stops_work_without_accepting_claims(tmp_path):
    run = execute(tmp_path, limits=Limits(max_tool_calls=1))
    assert run.tool_calls == 1
    assert not run.accepted
    assert run.status == "partial"


class SlowWorker(StubSpecialist):
    async def investigate(self, *args):
        await asyncio.sleep(0.1)
        return await super().investigate(*args)


def test_worker_timeout_is_visible_and_blocks_dependents(tmp_path):
    run = execute(tmp_path, worker=SlowWorker(), limits=Limits(call_timeout_s=0.01))
    assert run.status == "partial"
    assert run.tasks[1].status == "blocked"
    assert "TimeoutError" in run.report_markdown


class ChangingData(FixtureData):
    def __init__(self, change_on):
        super().__init__()
        self.calls, self.change_on = 0, change_on

    async def snapshot(self, workspace):
        scope = await super().snapshot(workspace)
        # read_source calls snapshot too; use a dedicated read method in this test.
        self.calls += 1
        if self.calls >= self.change_on:
            scope.snapshot_id = "new-snapshot"
        return scope

    async def read_source(self, scope, source_id):
        return await FixtureData().read_source(scope, source_id)


@pytest.mark.parametrize("change_on", [2, 3])
def test_snapshot_change_before_or_during_synthesis_blocks_publication(tmp_path, change_on):
    run = execute(tmp_path, data=ChangingData(change_on))
    assert run.status == "stale"
    assert not run.accepted
    assert "$4,000" not in run.report_markdown


class InventedNarrative(StubPlanner):
    def __init__(self, unknown):
        self.unknown = unknown

    async def synthesize(self, run):
        if self.unknown:
            return Narrative(items=[NarrativeItem(claim_id="invented", explanation="A claim.", proposed_next_step="Review.")])
        result = await super().synthesize(run)
        result.items[0].explanation = "We saved $900000."
        return result


@pytest.mark.parametrize("unknown", [True, False])
def test_bad_narrative_falls_back_to_reviewed_report(tmp_path, unknown):
    run = execute(tmp_path, model=InventedNarrative(unknown))
    assert run.status == "partial"
    assert "$900000" not in run.report_markdown
    assert "invented" not in run.report_markdown
    assert "$4,000.00" in run.report_markdown
    assert any(e.action == "synthesis.fallback" for e in run.events)


def test_restart_marks_pending_run_interrupted(tmp_path):
    repo = RunRepository(tmp_path / "runs.sqlite3")
    engine = CFOEngine(FixtureData(), {}, StubAuditor(), StubPlanner(), repo)
    run = engine.create(RunRequest())
    CFORuntime(repo)
    assert repo.get(run.id).status == "interrupted"


def test_runtime_refuses_runs_without_integrations_and_serializes_workspace(tmp_path, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(StructuredCFOModel, "from_env", lambda: StubPlanner())

    async def scenario():
        unconfigured = CFORuntime(RunRepository(tmp_path / "unconfigured.sqlite3"))
        with pytest.raises(HTTPException) as error:
            unconfigured.start(RunRequest())
        assert error.value.status_code == 503

        adapters = Adapters(FixtureData(), {r: StubSpecialist() for r in ["ap", "py", "gr"]}, StubAuditor())
        runtime = CFORuntime(RunRepository(tmp_path / "runs.sqlite3"), adapters)
        run = runtime.start(RunRequest())
        with pytest.raises(HTTPException) as error:
            runtime.start(RunRequest())
        assert error.value.status_code == 409
        await asyncio.gather(*list(runtime.pending.values()))
        assert runtime.repository.get(run.id).status == "completed"
        await runtime.close()

    asyncio.run(scenario())


def test_openai_adapter_uses_structured_output_and_records_usage():
    plan = Plan(memory_checks=[], rationale="Bounded check.", tasks=[TaskSpec(id="one", role="gr", objective="Read terms.", source_ids=["award"], success_criteria="Cite clause.")])
    parse = AsyncMock(return_value=SimpleNamespace(output_parsed=plan, usage=SimpleNamespace(input_tokens=100, output_tokens=50)))
    model = StructuredCFOModel("openai", "test-model", SimpleNamespace(responses=SimpleNamespace(parse=parse)))
    result = asyncio.run(model.plan("Check grant", asyncio.run(FixtureData().snapshot("test-workspace"))))
    assert result == plan
    assert parse.call_args.kwargs["store"] is False
    assert parse.call_args.kwargs["max_output_tokens"] == 4096
    assert model.input_tokens == 100


def test_local_adapter_never_uses_openai_secret(monkeypatch):
    import openai

    clients = []
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kwargs: clients.append(kwargs) or SimpleNamespace())
    monkeypatch.setenv("CFO_PROVIDER", "local")
    monkeypatch.setenv("CFO_MODEL", "local-qwen-test")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-must-not-be-forwarded")
    monkeypatch.setenv("CFO_LOCAL_BASE_URL", "http://127.0.0.1:11434/v1")
    StructuredCFOModel.from_env()
    assert clients[0]["api_key"] == "local-unused"
    monkeypatch.setenv("CFO_LOCAL_BASE_URL", "https://untrusted.example/v1")
    with pytest.raises(ValueError):
        StructuredCFOModel.from_env()
