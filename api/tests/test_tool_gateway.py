import pytest

from app.agents.tool_gateway import (
    AUDITOR_REGISTRY,
    AUDITOR_TOOL_SPECS,
    DEFAULT_BUDGET,
    TOOL_REGISTRY,
    TOOL_SPECS,
    ToolBudgetExceeded,
    ToolGateway,
    UnknownTool,
)
from app.models import ToolCall


def test_tool_specs_match_registry_one_to_one():
    assert {spec["name"] for spec in TOOL_SPECS} == set(TOOL_REGISTRY)


def test_tool_specs_use_openai_function_schema_shape():
    for spec in TOOL_SPECS:
        assert spec["type"] == "function"
        assert "parameters" in spec
        assert "input_schema" not in spec


def test_no_tool_schema_exposes_workspace():
    """workspace is bound by the orchestrator at gateway construction, never
    chosen by the model."""
    for spec in TOOL_SPECS:
        assert "workspace" not in spec["parameters"].get("properties", {})


def test_call_returns_json_safe_dict_for_a_single_record():
    gateway = ToolGateway()
    result = gateway.call("get_vendor", vendor_id="V-08")
    assert result == {
        "id": "V-08",
        "name": "Campus Supply Co.",
        "status": "active",
        "bank_account_last4": "4471",
        "bank_changed_at": None,
    }


def test_call_returns_json_safe_list_of_records():
    gateway = ToolGateway()
    result = gateway.call("list_invoices", vendor_id="V-08", status="matched")
    assert isinstance(result, list)
    assert {row["id"] for row in result} == {"INV-2291", "INV-2291A", "INV-3102", "INV-3102B"}


def test_call_returns_json_safe_composite_packet():
    gateway = ToolGateway()
    result = gateway.call("get_invoice_packet", invoice_id="INV-2302")
    assert result["invoice"]["id"] == "INV-2302"
    assert result["vendor"]["bank_changed_at"] == "2026-09-27"


def test_unknown_tool_raises_without_spending_budget():
    gateway = ToolGateway(budget=5)
    with pytest.raises(UnknownTool):
        gateway.call("delete_everything")
    assert gateway.used == 0
    assert gateway.remaining == 5


def test_invalid_arguments_return_error_and_still_spend_budget():
    gateway = ToolGateway(budget=5)
    result = gateway.call("get_vendor", not_a_real_param="x")
    assert "error" in result
    assert gateway.used == 1


def test_filesystem_error_is_correctable_not_a_crash():
    """Regression: record_decision's store writes raise a real OSError when
    `workspace` is an arbitrary filesystem path rather than a SchoolTrace
    bundle id (e.g. the AR reconciliation task's workspace directory). A
    tool that touches the filesystem must degrade to an {"error": ...}
    payload like every other tool failure, not crash the whole run — and,
    since this can happen inside a nested specialist run started via
    assign_task, it would otherwise crash the CFO's run too."""

    def touches_disk(**_ignored):
        raise FileNotFoundError("no such bundle for this workspace")

    gateway = ToolGateway(registry={"touches_disk": touches_disk}, budget=3)
    result = gateway.call("touches_disk")
    assert "error" in result
    assert gateway.used == 1


def test_budget_exhausts_and_refuses_further_calls():
    gateway = ToolGateway(budget=2)
    gateway.call("get_vendor", vendor_id="V-08")
    gateway.call("get_vendor", vendor_id="V-03")
    assert gateway.remaining == 0
    with pytest.raises(ToolBudgetExceeded):
        gateway.call("get_vendor", vendor_id="V-12")
    assert gateway.used == 2


def test_default_budget_matches_spec():
    assert ToolGateway().budget == DEFAULT_BUDGET == 12


def test_two_gateways_have_independent_budgets():
    """Two concurrent specialists (e.g. AP and Payroll) must never share a
    counter — one running hot can't starve the other."""
    ap_gateway = ToolGateway(budget=1)
    py_gateway = ToolGateway(budget=1)
    ap_gateway.call("get_vendor", vendor_id="V-08")
    assert ap_gateway.remaining == 0
    assert py_gateway.remaining == 1
    py_gateway.call("get_vendor", vendor_id="V-08")
    assert py_gateway.remaining == 0


def test_auditor_specs_match_auditor_registry_one_to_one():
    assert {spec["name"] for spec in AUDITOR_TOOL_SPECS} == set(AUDITOR_REGISTRY)


def test_auditor_registry_has_no_ap_write_tools():
    """The auditor can re-check with the same reads, but must not be able to
    submit_finding or prepare_payment_batch — only submit_review."""
    assert "submit_review" in AUDITOR_REGISTRY
    assert "submit_finding" not in AUDITOR_REGISTRY
    assert "prepare_payment_batch" not in AUDITOR_REGISTRY
    assert "get_invoice" in AUDITOR_REGISTRY  # shares the reads


def test_gateway_defaults_to_ap_registry():
    gateway = ToolGateway()
    assert gateway.registry == TOOL_REGISTRY


def test_gateway_can_be_scoped_to_a_different_registry():
    gateway = ToolGateway(registry=AUDITOR_REGISTRY)
    with pytest.raises(UnknownTool):
        gateway.call("submit_finding", title="t", summary="s", status="substantiated", evidence=[])
    result = gateway.call("get_invoice", invoice_id="INV-2291")
    assert result["id"] == "INV-2291"


def test_mutating_one_gateways_registry_does_not_leak_to_another():
    gateway_a = ToolGateway()
    gateway_a.registry["extra"] = lambda **_: "unused"
    gateway_b = ToolGateway()
    assert "extra" not in gateway_b.registry
    assert "extra" not in TOOL_REGISTRY


def test_decision_log_entries_are_valid_tool_call_records():
    gateway = ToolGateway()
    gateway.call("get_vendor", vendor_id="V-08")
    gateway.call("find_duplicate_candidates", invoice_id="INV-2291")
    log = gateway.as_decision_log()
    assert len(log) == 2
    for entry in log:
        call = ToolCall.model_validate(entry)
        assert call.tool in {"get_vendor", "find_duplicate_candidates"}
    assert log[0]["input"] == "vendor_id='V-08'"
    assert log[1]["output"] == "3 results"
