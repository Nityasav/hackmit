import json
from types import SimpleNamespace

import pytest

from app import store
from app.agents.run_loop import run_ap_agent, run_auditor_agent


@pytest.fixture(autouse=True)
def fresh_bundle():
    store.reset()
    yield
    store.reset()


def _function_call(name, args, call_id):
    return SimpleNamespace(type="function_call", name=name, arguments=json.dumps(args), call_id=call_id)


def test_rejected_review_submission_never_marks_task_done():
    task_id = _new_task(agent="au")
    fake = FakeClient([
        FakeResponse([_function_call("submit_review", {"finding_id": "D-99", "decision": "accept", "evidence_note": "Read records"}, "bad-review")]),
        FakeResponse([], "Could not file review"),
    ])
    run_auditor_agent("Review finding", client=fake, task_id=task_id)
    task = next(t for t in store.get_bundle("sandbox").tasks if t.id == task_id)
    assert task.column == "needs_you"


class FakeResponse:
    def __init__(self, output, output_text=""):
        self.output = output
        self.output_text = output_text


class FakeResponses:
    def __init__(self, responses):
        self._responses = list(responses)

    def create(self, **kwargs):
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.responses = FakeResponses(responses)


def _new_task(agent="ap", budget=12) -> str:
    task_id = "T-900"
    store.create_task(
        "sandbox",
        {
            "id": task_id,
            "agent": agent,
            "title": "test task",
            "workflow": "AP & payments",
            "column": "working",
            "progress": 0,
            "eta_s": None,
            "started_at": "14:00:00",
            "tool_calls": {"used": 0, "budget": budget},
            "steps": [],
            "todos": [],
            "rationale": None,
        },
    )
    return task_id


def test_task_progress_updates_live_during_the_run():
    task_id = _new_task()
    fake = FakeClient(
        [
            FakeResponse(output=[_function_call("get_vendor", {"vendor_id": "V-08"}, "call_1")]),
            FakeResponse(output=[], output_text="Done."),
        ]
    )

    run_ap_agent("Look up V-08", client=fake, task_id=task_id)

    bundle = store.get_bundle("sandbox")
    task = next(t for t in bundle.tasks if t.id == task_id)
    assert task.tool_calls.used == 1
    assert len(task.steps) == 1
    assert task.steps[0].title == "get_vendor"


def test_completed_run_with_a_filed_finding_lands_in_auditor_review():
    task_id = _new_task()
    fake = FakeClient(
        [
            FakeResponse(
                output=[
                    _function_call(
                        "submit_finding",
                        {
                            "title": "t",
                            "summary": "s",
                            "status": "substantiated",
                            "evidence": [{"label": "x", "kind": "record", "tone": "bad"}],
                        },
                        "call_1",
                    )
                ]
            ),
            FakeResponse(output=[], output_text="Filed."),
        ]
    )

    run_ap_agent("Investigate", client=fake, task_id=task_id)

    task = next(t for t in store.get_bundle("sandbox").tasks if t.id == task_id)
    assert task.column == "auditor_review"
    assert task.progress == 100


def test_completed_run_with_evidence_request_lands_in_needs_you():
    task_id = _new_task()
    fake = FakeClient(
        [
            FakeResponse(output=[_function_call("request_evidence", {"title": "t", "summary": "s"}, "call_1")]),
            FakeResponse(output=[], output_text="Asked."),
        ]
    )

    run_ap_agent("Investigate", client=fake, task_id=task_id)

    task = next(t for t in store.get_bundle("sandbox").tasks if t.id == task_id)
    assert task.column == "needs_you"
    assert task.note_tone == "warn"


def test_completed_run_with_no_write_calls_lands_in_done():
    task_id = _new_task()
    fake = FakeClient(
        [
            FakeResponse(output=[_function_call("get_vendor", {"vendor_id": "V-08"}, "call_1")]),
            FakeResponse(output=[], output_text="No issues found."),
        ]
    )

    run_ap_agent("Look up V-08", client=fake, task_id=task_id)

    task = next(t for t in store.get_bundle("sandbox").tasks if t.id == task_id)
    assert task.column == "done"
    assert task.rationale == "No issues found."


def test_max_turns_exceeded_lands_in_needs_you_with_a_note():
    task_id = _new_task()
    fake = FakeClient(
        [
            FakeResponse(output=[_function_call("get_vendor", {"vendor_id": "V-08"}, "call_1")]),
            FakeResponse(output=[_function_call("get_vendor", {"vendor_id": "V-08"}, "call_2")]),
        ]
    )

    run_ap_agent("Keep looking", client=fake, task_id=task_id, max_turns=2)

    task = next(t for t in store.get_bundle("sandbox").tasks if t.id == task_id)
    assert task.column == "needs_you"
    assert "ran out of turns" in task.note


def test_auditor_task_that_never_files_a_review_is_not_done():
    """Regression: a live run had the auditor burn its whole tool budget
    investigating and never reach submit_review. The task still showed as
    'done' under the old default-to-done logic, which misrepresented a stuck
    review as a finished one. Only an actual submit_review call earns done."""
    task_id = _new_task(agent="au")
    fake = FakeClient(
        [
            FakeResponse(output=[_function_call("get_invoice", {"invoice_id": "INV-2302"}, "call_1")]),
            FakeResponse(output=[], output_text="Ran out of budget before filing a review."),
        ]
    )

    run_auditor_agent("Review F-11", client=fake, task_id=task_id)

    task = next(t for t in store.get_bundle("sandbox").tasks if t.id == task_id)
    assert task.column == "needs_you"
    assert "Review not filed" in task.note


def test_auditor_review_landing_in_done():
    from app.agents import ap_write_tools

    finding_id = ap_write_tools.submit_finding(
        title="t", summary="s", status="substantiated", evidence=[{"label": "x", "kind": "record", "tone": "bad"}]
    )["finding_id"]
    task_id = _new_task(agent="au")

    fake = FakeClient(
        [
            FakeResponse(
                output=[
                    _function_call(
                        "submit_review",
                        {"finding_id": finding_id, "decision": "accept", "evidence_note": "Re-checked."},
                        "call_1",
                    )
                ]
            ),
            FakeResponse(output=[], output_text="Accepted."),
        ]
    )

    run_auditor_agent(f"Review {finding_id}", client=fake, task_id=task_id)

    task = next(t for t in store.get_bundle("sandbox").tasks if t.id == task_id)
    assert task.column == "done"


def test_run_without_task_id_does_not_touch_the_board():
    """The common case (standalone question, no assign_task) must not create
    or require any task — this is purely additive."""
    fake = FakeClient([FakeResponse(output=[], output_text="Answer.")])
    before = len(store.get_bundle("sandbox").tasks)

    run_ap_agent("Quick question", client=fake)

    after = len(store.get_bundle("sandbox").tasks)
    assert before == after
