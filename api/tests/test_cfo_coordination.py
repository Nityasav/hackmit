import asyncio

from app.cfo.engine import CFOEngine
from app.cfo.repository import RunRepository
from app.cfo.schemas import Claim, Plan, RunRequest, TaskSpec, WorkerResult
from tests.conftest import FixtureData, StubAuditor, StubPlanner, StubSpecialist


class IndependentPlan(StubPlanner):
    async def plan(self, objective, scope):
        return Plan(rationale="Independent evidence checks can run concurrently.", tasks=[
            TaskSpec(id=f"task-{i}", role=role, objective="Check award terms.", source_ids=["award"], success_criteria="Cite original evidence.")
            for i, role in enumerate(["ap", "py", "gr"])
        ])


class CountingWorker:
    def __init__(self):
        self.active = self.peak = 0

    async def investigate(self, task, scope, tools, dependencies, feedback):
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0.01)
            await tools.read_source("award")
            return WorkerResult(summary="Evidence checked.", claims=[Claim(
                id=task.id + "-claim", event_key=task.id, title="Award terms", conclusion="Service evidence is required.",
                disposition="explained", evidence_ids=["award"])])
        finally:
            self.active -= 1


def test_independent_tasks_run_with_bounded_parallelism(tmp_path):
    worker = CountingWorker()
    engine = CFOEngine(FixtureData(), {r: worker for r in ["ap", "py", "gr"]}, StubAuditor(), IndependentPlan(), RunRepository(tmp_path / "runs.sqlite3"))
    run = asyncio.run(engine.execute(engine.create(RunRequest())))
    assert run.status == "completed"
    assert worker.peak == 2
    assert len(run.accepted) == 3


class DuplicateWorker(CountingWorker):
    def __init__(self, conflict):
        super().__init__()
        self.conflict = conflict

    async def investigate(self, *args):
        result = await super().investigate(*args)
        result.claims[0].event_key = "same-economic-event"
        if self.conflict and args[0].role == "py":
            result.claims[0].conclusion = "The award criterion is ambiguous."
        return result


def test_duplicate_economic_events_are_not_double_counted(tmp_path):
    worker = DuplicateWorker(False)
    engine = CFOEngine(FixtureData(), {r: worker for r in ["ap", "py", "gr"]}, StubAuditor(), IndependentPlan(), RunRepository(tmp_path / "runs.sqlite3"))
    run = asyncio.run(engine.execute(engine.create(RunRequest())))
    assert len(run.accepted) == 1


def test_disagreement_is_preserved_and_withheld_from_confirmed_report(tmp_path):
    worker = DuplicateWorker(True)
    engine = CFOEngine(FixtureData(), {r: worker for r in ["ap", "py", "gr"]}, StubAuditor(), IndependentPlan(), RunRepository(tmp_path / "runs.sqlite3"))
    run = asyncio.run(engine.execute(engine.create(RunRequest())))
    assert not run.accepted
    assert run.status == "needs_evidence"
    assert "Conflicting or ambiguous" in run.report_markdown
    assert any("ambiguous" in e.detail for e in run.events)


class EscapingWorker(StubSpecialist):
    async def investigate(self, task, scope, tools, dependencies, feedback):
        await tools.read_source("private-other-school")
        return await super().investigate(task, scope, tools, dependencies, feedback)


def test_worker_cannot_expand_authorized_source_scope(tmp_path):
    engine = CFOEngine(FixtureData(), {r: EscapingWorker() for r in ["ap", "py", "gr"]}, StubAuditor(), StubPlanner(), RunRepository(tmp_path / "runs.sqlite3"))
    run = asyncio.run(engine.execute(engine.create(RunRequest())))
    assert run.status == "partial"
    assert run.tool_calls == 0
    assert not run.accepted
