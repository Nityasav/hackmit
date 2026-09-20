"""Precedent reaches the five-agent coordinator, and cannot be forged there.

The loop already existed on the triage path in `agents/cfo.py`. The coordinator
behind `POST /api/cfo/runs` — the one the Investigation screen calls — had no
reference to precedent at all, so the screen showed decisions a human had made
and nothing about whether any run had ever reckoned with them.

These cover the half that is a safety property rather than a feature: a run may
read precedent and count a use, and may not invent one.
"""

import asyncio

from app.cfo.engine import CFOEngine
from app.cfo.repository import RunRepository
from app.cfo.schemas import Claim, MemoryCheck, Plan, Precedent, RunRequest, TaskSpec, WorkerResult
from tests.conftest import FixtureData, StubAuditor, StubPlanner, StubSpecialist

PRECEDENT = Precedent(
    id="PB-realone", pattern="Invoice without purchase-order reference",
    verdict="approved", guidance="Re-check against the current snapshot before relying on this.",
)


class PlanWithChecks(StubPlanner):
    """A planner that reports whatever memory checks a test hands it."""

    def __init__(self, checks):
        self.checks = checks
        self.seen_precedents = None

    async def plan(self, objective, scope):
        self.seen_precedents = [p.id for p in scope.precedents]
        return Plan(memory_checks=self.checks, rationale="Bounded check.", tasks=[
            TaskSpec(id="task-1", role="gr", objective="Read terms.",
                     source_ids=["award"], success_criteria="Cite original evidence."),
        ])


class Worker:
    async def investigate(self, task, scope, tools, dependencies, feedback):
        await tools.read_source("award")
        return WorkerResult(summary="Evidence checked.", claims=[Claim(
            id="c-1", event_key="k", title="Award terms",
            conclusion="Service evidence is required.", disposition="explained",
            evidence_ids=["award"])])


def _run(tmp_path, planner, data):
    engine = CFOEngine(data, {r: Worker() for r in ["ap", "py", "gr"]},
                       StubAuditor(), planner, RunRepository(tmp_path / "runs.sqlite3"))
    return asyncio.run(engine.execute(engine.create(RunRequest())))


def test_the_planner_is_offered_the_workspace_precedent(tmp_path):
    planner = PlanWithChecks([MemoryCheck(precedent_id="PB-realone", applied=True, reason="Same situation.")])
    _run(tmp_path, planner, FixtureData(precedents=[PRECEDENT]))
    assert planner.seen_precedents == ["PB-realone"]


def test_a_declined_precedent_is_recorded_as_prominently_as_an_applied_one(tmp_path):
    """Declining is the mechanism working. If only applications were kept, a
    correctly cautious run would look like one that never checked."""
    planner = PlanWithChecks([MemoryCheck(
        precedent_id="PB-realone", applied=False,
        reason="The current snapshot adds a second invoice; not the same situation.")])
    run = _run(tmp_path, planner, FixtureData(precedents=[PRECEDENT]))

    assert [(c.precedent_id, c.applied) for c in run.memory_checks] == [("PB-realone", False)]
    assert any(e.action == "memory.declined" for e in run.events)


def test_a_run_cannot_invent_a_precedent_it_was_never_offered(tmp_path):
    """The safety property. A model can put any string in `precedent_id`. Taken
    at face value, a run could manufacture its own memory — claim it consulted
    guidance nobody gave, and have it counted and shown as a human decision."""
    planner = PlanWithChecks([
        MemoryCheck(precedent_id="PB-realone", applied=True, reason="Same situation."),
        MemoryCheck(precedent_id="PB-invented", applied=True, reason="Asserting this exists."),
    ])
    data = FixtureData(precedents=[PRECEDENT])
    run = _run(tmp_path, planner, data)

    assert [c.precedent_id for c in run.memory_checks] == ["PB-realone"]
    assert any("PB-invented" in item for item in run.unresolved)
    # And the forged one is never counted as a use.
    assert data.noted_uses == [(run.request.workspace, ["PB-realone"])]


def test_weighing_a_precedent_counts_as_using_it(tmp_path):
    planner = PlanWithChecks([MemoryCheck(
        precedent_id="PB-realone", applied=False, reason="Evidence differs.")])
    data = FixtureData(precedents=[PRECEDENT])
    run = _run(tmp_path, planner, data)

    assert data.noted_uses == [(run.request.workspace, ["PB-realone"])]


def test_an_unaddressed_precedent_does_not_pass_as_considered(tmp_path):
    """Silence is not a check. A run offered guidance that never mentions it
    has not re-checked anything, and should not read as though it had."""
    planner = PlanWithChecks([])
    data = FixtureData(precedents=[PRECEDENT])
    run = _run(tmp_path, planner, data)

    assert run.memory_checks == []
    assert any("PB-realone" in item and "not addressed" in item for item in run.unresolved)
    assert data.noted_uses == []


def test_a_workspace_with_no_precedent_is_unaffected(tmp_path):
    planner = PlanWithChecks([])
    data = FixtureData()
    run = _run(tmp_path, planner, data)

    assert run.status == "completed"
    assert run.memory_checks == []
    assert data.noted_uses == []


def test_a_run_stored_before_memory_checks_existed_still_loads(tmp_path):
    """Found by restarting the server against its real database, not by a test.

    `interrupt_pending()` validates every stored row at startup, so one run
    written before the field shipped made the whole coordinator answer 500 —
    while every test passed, because each builds its database from scratch.
    """
    import json

    repository = RunRepository(tmp_path / "runs.sqlite3")
    run = _run(tmp_path, PlanWithChecks([]), FixtureData())

    # Rewrite the row the way the old code wrote it: no memory_checks anywhere.
    payload = json.loads(run.model_dump_json())
    del payload["memory_checks"]
    del payload["plan"]["memory_checks"]
    with repository._connect() as connection:
        connection.execute(
            "INSERT INTO cfo_runs VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
            (run.id, run.request.workspace, run.created_at, json.dumps(payload)))

    loaded = repository.get(run.id)
    assert loaded.memory_checks == []
    assert loaded.plan.memory_checks == []
    repository.interrupt_pending()  # must not raise


def test_the_plan_schema_still_requires_memory_checks():
    """The loader above tolerates legacy rows; it must not have quietly made
    the field optional for the model, which is what keeps a silent omission
    from reading as a completed check."""
    schema = Plan.model_json_schema()
    assert "memory_checks" in schema["required"]
