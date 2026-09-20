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


class FakeResponse:
    """Mimics an OpenAI Responses API response: .output is a list of items,
    .output_text is the SDK's convenience property for the final text."""

    def __init__(self, output, output_text=""):
        self.output = output
        self.output_text = output_text


class FakeResponses:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        # Snapshot input: run_ap_agent keeps mutating the same list object
        # after this call returns, so a bare reference would show later state.
        self.calls.append({**kwargs, "input": list(kwargs["input"])})
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.responses = FakeResponses(responses)


def test_single_tool_call_then_final_answer():
    fake = FakeClient(
        [
            FakeResponse(output=[_function_call("get_invoice", {"invoice_id": "INV-2302"}, "call_1")]),
            FakeResponse(output=[], output_text="INV-2302 is held: vendor V-12 changed bank details."),
        ]
    )

    result = run_ap_agent("Should INV-2302 be paid?", client=fake)

    assert result.stop_reason == "completed"
    assert result.answer == "INV-2302 is held: vendor V-12 changed bank details."
    assert result.tool_calls_used == 1
    assert result.tool_calls[0]["tool"] == "get_invoice"

    # The second request must carry back a real, correct function_call_output for call_1.
    second_request = fake.responses.calls[1]
    function_call_output = second_request["input"][-1]
    assert function_call_output["type"] == "function_call_output"
    assert function_call_output["call_id"] == "call_1"
    payload = json.loads(function_call_output["output"])
    assert payload["id"] == "INV-2302"
    assert payload["status"] == "held"


def test_unknown_tool_reports_error_without_crashing():
    fake = FakeClient(
        [
            FakeResponse(output=[_function_call("delete_everything", {}, "call_1")]),
            FakeResponse(output=[], output_text="I can't do that."),
        ]
    )

    result = run_ap_agent("Delete all invoices", client=fake)

    assert result.stop_reason == "completed"
    assert result.tool_calls_used == 0  # nothing ran, so no budget was spent
    assert result.tool_calls == []

    second_request = fake.responses.calls[1]
    function_call_output = second_request["input"][-1]
    assert "unknown tool" in function_call_output["output"]


def test_exhausted_budget_reports_error_and_lets_model_finish():
    fake = FakeClient(
        [
            FakeResponse(output=[_function_call("get_vendor", {"vendor_id": "V-08"}, "call_1")]),
            FakeResponse(output=[_function_call("get_vendor", {"vendor_id": "V-03"}, "call_2")]),
            FakeResponse(output=[], output_text="Ran out of budget."),
        ]
    )

    result = run_ap_agent("Look up two vendors", budget=1, client=fake)

    assert result.tool_calls_used == 1  # only the first call actually spent budget
    assert result.stop_reason == "completed"

    third_request = fake.responses.calls[2]
    second_function_call_output = third_request["input"][-1]
    assert second_function_call_output["call_id"] == "call_2"
    assert "tool budget exhausted" in second_function_call_output["output"]


def test_max_turns_exceeded_stops_honestly_instead_of_fabricating():
    fake = FakeClient(
        [
            FakeResponse(output=[_function_call("get_vendor", {"vendor_id": "V-08"}, "call_1")]),
            FakeResponse(output=[_function_call("get_vendor", {"vendor_id": "V-08"}, "call_2")]),
        ]
    )

    result = run_ap_agent("Keep looking", max_turns=2, budget=12, client=fake)

    assert result.stop_reason == "max_turns_exceeded"
    assert result.tool_calls_used == 2
    assert result.answer == ""  # no text was ever produced


def test_malformed_arguments_report_error_without_crashing():
    bad_call = SimpleNamespace(type="function_call", name="get_vendor", arguments="{not json", call_id="call_1")
    fake = FakeClient(
        [
            FakeResponse(output=[bad_call]),
            FakeResponse(output=[], output_text="Couldn't parse that."),
        ]
    )

    result = run_ap_agent("Look up a vendor", client=fake)

    assert result.stop_reason == "completed"
    assert result.tool_calls_used == 0
    second_request = fake.responses.calls[1]
    assert "invalid arguments JSON" in second_request["input"][-1]["output"]


def test_immediate_final_answer_with_no_tool_calls():
    fake = FakeClient([FakeResponse(output=[], output_text="Quick answer, no lookups needed.")])

    result = run_ap_agent("Quick question", client=fake)

    assert result.answer == "Quick answer, no lookups needed."
    assert result.tool_calls_used == 0


def test_record_decision_files_a_real_decision_and_is_captured_on_the_result():
    fake = FakeClient(
        [
            FakeResponse(
                output=[
                    _function_call(
                        "record_decision",
                        {
                            "action": "Checked INV-2302",
                            "summary": "Vendor bank details changed recently.",
                            "why": "A bank change right before payment is a control risk.",
                            "alternatives": [{"option": "Pay it", "reason": "amount matches PO", "chosen": False}],
                            "memory_checks": [],
                            "outcome": "Held pending verification.",
                        },
                        "call_1",
                    )
                ]
            ),
            FakeResponse(output=[], output_text="Filed."),
        ]
    )

    result = run_ap_agent("Should INV-2302 be paid?", client=fake)

    assert result.decision_id is not None
    bundle = store.get_bundle("sandbox")
    filed = next(d for d in bundle.decisions if d.id == result.decision_id)
    assert filed.agent == "ap"
    assert filed.why == "A bank change right before payment is a control risk."
    assert filed.when.trigger == "Should INV-2302 be paid?"


def test_record_decision_how_reflects_the_actual_tool_calls_made():
    fake = FakeClient(
        [
            FakeResponse(output=[_function_call("get_vendor", {"vendor_id": "V-08"}, "call_1")]),
            FakeResponse(
                output=[
                    _function_call(
                        "record_decision",
                        {
                            "action": "Checked vendor",
                            "summary": "s",
                            "why": "w",
                            "alternatives": [],
                            "memory_checks": [],
                            "outcome": "o",
                        },
                        "call_2",
                    )
                ]
            ),
            FakeResponse(output=[], output_text="Done."),
        ]
    )

    result = run_ap_agent("Look up V-08", client=fake)

    bundle = store.get_bundle("sandbox")
    filed = next(d for d in bundle.decisions if d.id == result.decision_id)
    assert len(filed.how) == 1
    assert filed.how[0].tool == "get_vendor"


def test_run_auditor_agent_can_accept_a_finding_via_submit_review():
    from app.agents import ap_write_tools

    finding_id = ap_write_tools.submit_finding(
        title="t",
        summary="s",
        status="substantiated",
        evidence=[{"label": "x", "kind": "record", "tone": "bad"}],
    )["finding_id"]

    fake = FakeClient(
        [
            FakeResponse(
                output=[
                    _function_call(
                        "submit_review",
                        {"finding_id": finding_id, "decision": "accept", "evidence_note": "Re-checked the PO."},
                        "call_1",
                    )
                ]
            ),
            FakeResponse(output=[], output_text="Accepted."),
        ]
    )

    result = run_auditor_agent(f"Independently review {finding_id}.", client=fake)

    assert result.tool_calls_used == 1
    bundle = store.get_bundle("sandbox")
    filed = next(f for f in bundle.findings if f.id == finding_id)
    assert filed.verified_by == "au"


def test_run_auditor_agent_cannot_reach_ap_write_tools():
    fake = FakeClient(
        [
            FakeResponse(output=[_function_call("submit_finding", {}, "call_1")]),
            FakeResponse(output=[], output_text="Can't do that."),
        ]
    )

    result = run_auditor_agent("Try to file a finding", client=fake)

    second_request = fake.responses.calls[1]
    assert "unknown tool" in second_request["input"][-1]["output"]
    assert result.tool_calls_used == 0
