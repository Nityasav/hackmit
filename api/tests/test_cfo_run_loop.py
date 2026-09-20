import json
from types import SimpleNamespace

import pytest

from app import store
from app.agents.run_loop import run_cfo_agent


@pytest.fixture(autouse=True)
def fresh_bundle():
    store.reset()
    yield
    store.reset()


def _function_call(name, args, call_id):
    return SimpleNamespace(type="function_call", name=name, arguments=json.dumps(args), call_id=call_id)


class FakeResponse:
    def __init__(self, output, output_text=""):
        self.output = output
        self.output_text = output_text


class FakeResponses:
    """One shared queue. assign_task calls the same client synchronously from
    inside a CFO tool call, so CFO turns and specialist turns interleave in
    the exact order they're actually requested — the queue must match that."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append({**kwargs, "input": list(kwargs["input"])})
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.responses = FakeResponses(responses)


def test_assign_task_creates_a_task_and_runs_the_specialist_synchronously():
    fake = FakeClient(
        [
            # CFO turn 1: assign a task to AP
            FakeResponse(
                output=[
                    _function_call(
                        "assign_task",
                        {
                            "agent": "ap",
                            "title": "Check INV-2302",
                            "workflow": "AP & payments",
                            "question": "Should INV-2302 be paid?",
                        },
                        "cfo_call_1",
                    )
                ]
            ),
            # AP specialist turn 1 (inside assign_task)
            FakeResponse(output=[_function_call("get_vendor", {"vendor_id": "V-12"}, "ap_call_1")]),
            # AP specialist turn 2: done
            FakeResponse(output=[], output_text="INV-2302 should not be paid yet."),
            # CFO turn 2: done
            FakeResponse(output=[], output_text="Assigned and reviewed."),
        ]
    )

    result = run_cfo_agent("Should INV-2302 be paid?", client=fake)

    assert result.stop_reason == "completed"
    assert result.answer == "Assigned and reviewed."
    assert result.tool_calls_used == 1  # only assign_task counted against the CFO's own budget

    bundle = store.get_bundle("sandbox")
    tasks = [t for t in bundle.tasks if t.title == "Check INV-2302"]
    assert len(tasks) == 1
    assert tasks[0].agent == "ap"
    assert tasks[0].column == "done"  # AP only read, filed nothing


def test_handoff_returns_finding_ids_not_just_decision_id(monkeypatch):
    from app.agents import ap_write_tools, run_loop
    from app.agents.cfo_tools import bind_assign_task

    def specialist(*args, **kwargs):
        ap_write_tools.submit_finding("Review INV-2302", "Needs review", "needs_evidence",
                                     [{"label": "INV-2302", "kind": "record", "tone": "neutral"}])
        return SimpleNamespace(answer="Filed", decision_id="D-99", tool_calls_used=1)
    monkeypatch.setattr(run_loop, "run_ap_agent", specialist)
    assign = bind_assign_task(workspace="sandbox", client=None, specialist_budget=12)
    result = assign(agent="ap", title="review", workflow="ap", question="Investigate")
    assert result["finding_ids"] == ["F-11"]
    assert result["decision_id"] == "D-99"


def test_assign_task_result_reports_specialist_answer_back_to_cfo():
    fake = FakeClient(
        [
            FakeResponse(
                output=[
                    _function_call(
                        "assign_task",
                        {"agent": "ap", "title": "t", "workflow": "w", "question": "q"},
                        "cfo_call_1",
                    )
                ]
            ),
            FakeResponse(output=[], output_text="Specialist's real answer."),
            FakeResponse(output=[], output_text="cfo done"),
        ]
    )

    run_cfo_agent("q", client=fake)

    # The CFO's next request must carry the specialist's actual answer back, not a placeholder.
    third_request = fake.responses.calls[2]
    function_call_output = third_request["input"][-1]
    payload = json.loads(function_call_output["output"])
    assert payload["specialist_answer"] == "Specialist's real answer."
    assert payload["column"] == "done"


def test_assign_task_rejects_an_unknown_specialist_without_creating_a_task():
    fake = FakeClient(
        [
            FakeResponse(
                output=[
                    _function_call(
                        "assign_task",
                        {"agent": "py", "title": "t", "workflow": "w", "question": "q"},
                        "cfo_call_1",
                    )
                ]
            ),
            FakeResponse(output=[], output_text="Don't have that specialist yet."),
        ]
    )
    before = len(store.get_bundle("sandbox").tasks)

    run_cfo_agent("q", client=fake)

    after = len(store.get_bundle("sandbox").tasks)
    assert before == after


def test_write_briefing_replaces_the_bundle_briefing():
    fake = FakeClient(
        [
            FakeResponse(
                output=[
                    _function_call(
                        "write_briefing",
                        {"text": "**1 issue** found.", "actions": [{"label": "Review", "href": "approvals"}]},
                        "call_1",
                    )
                ]
            ),
            FakeResponse(output=[], output_text="Briefing written."),
        ]
    )

    run_cfo_agent("Summarize the investigation", client=fake)

    bundle = store.get_bundle("sandbox")
    assert "1 issue" in bundle.briefing.text
    assert bundle.briefing.actions[0].label == "Review"


def test_cfo_budget_is_independent_of_specialist_budget():
    """The CFO's own gateway only counts assign_task/write_briefing calls —
    the specialist's internal tool calls spend a completely separate budget."""
    fake = FakeClient(
        [
            FakeResponse(
                output=[
                    _function_call(
                        "assign_task",
                        {"agent": "ap", "title": "t", "workflow": "w", "question": "q"},
                        "cfo_call_1",
                    )
                ]
            ),
            FakeResponse(output=[_function_call("get_vendor", {"vendor_id": "V-08"}, "ap_call_1")]),
            FakeResponse(output=[_function_call("get_vendor", {"vendor_id": "V-03"}, "ap_call_2")]),
            FakeResponse(output=[], output_text="specialist done"),
            FakeResponse(output=[], output_text="cfo done"),
        ]
    )

    result = run_cfo_agent("q", client=fake, budget=1, specialist_budget=12)

    assert result.tool_calls_used == 1
    assert result.stop_reason == "completed"


def test_cfo_own_decision_is_recorded():
    fake = FakeClient(
        [
            FakeResponse(
                output=[
                    _function_call(
                        "record_decision",
                        {
                            "action": "Planned investigation",
                            "summary": "Assigned one AP task.",
                            "why": "The question is scoped to a single invoice.",
                            "alternatives": [],
                            "memory_checks": [],
                            "outcome": "Task assigned.",
                        },
                        "call_1",
                    )
                ]
            ),
            FakeResponse(output=[], output_text="Done."),
        ]
    )

    result = run_cfo_agent("Should INV-2302 be paid?", client=fake)

    assert result.decision_id is not None
    bundle = store.get_bundle("sandbox")
    filed = next(d for d in bundle.decisions if d.id == result.decision_id)
    assert filed.agent == "cfo"
