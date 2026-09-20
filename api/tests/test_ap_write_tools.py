import pytest

from app import store
from app.agents import ap_write_tools
from app.agents import ap_tools
from app.agents.ap_records import Approval
from app.agents.tool_gateway import ToolGateway


@pytest.fixture(autouse=True)
def fresh_bundle():
    """The store is module-level mutable state; each test gets a clean bundle."""
    store.reset()
    yield
    store.reset()


EVIDENCE = [
    {"label": "INV-2317 - $3,200.00", "kind": "record", "tone": "neutral", "edge": "MATCHED_TO"},
    {"label": "PO-889 line 1", "kind": "doc", "tone": "good"},
]


def test_submit_finding_lands_in_the_bundle():
    result = ap_write_tools.submit_finding(
        title="INV-2317 has no goods receipt",
        summary="Invoice matches PO-889 on amount, but no receipt is recorded.",
        status="needs_evidence",
        evidence=EVIDENCE,
    )

    bundle = store.get_bundle("sandbox")
    filed = next(f for f in bundle.findings if f.id == result["finding_id"])
    assert filed.agent == "ap"
    assert filed.title == "INV-2317 has no goods receipt"
    assert filed.status == "needs_evidence"


def test_finding_id_continues_the_existing_sequence():
    result = ap_write_tools.submit_finding(
        title="t", summary="s", status="needs_evidence", evidence=EVIDENCE
    )
    # Fixture ships F-07..F-10.
    assert result["finding_id"] == "F-11"


def test_agent_cannot_mark_its_own_finding_verified():
    """Separation of duties: only the Internal Auditor sets verified_by."""
    result = ap_write_tools.submit_finding(
        title="t", summary="s", status="substantiated", evidence=EVIDENCE
    )
    bundle = store.get_bundle("sandbox")
    filed = next(f for f in bundle.findings if f.id == result["finding_id"])
    assert filed.verified_by is None
    assert result["verified_by"] is None


def test_finding_without_evidence_is_rejected():
    with pytest.raises(ValueError, match="evidence"):
        ap_write_tools.submit_finding(title="t", summary="s", status="substantiated", evidence=[])


def test_amount_without_a_note_is_rejected():
    with pytest.raises(ValueError, match="amount_note"):
        ap_write_tools.submit_finding(
            title="t", summary="s", status="substantiated", evidence=EVIDENCE, amount_cents=400000
        )


def test_request_evidence_queues_a_pending_approval():
    result = ap_write_tools.request_evidence(
        title="Upload signed delivery slip for PO-889",
        summary="Needed to complete the 3-way match on INV-2317.",
    )

    bundle = store.get_bundle("sandbox")
    queued = next(a for a in bundle.approvals if a.id == result["approval_id"])
    assert queued.kind == "evidence"
    assert queued.status == "pending"
    assert queued.verified is False


def test_payment_batch_includes_clean_invoices_and_holds_flagged_ones():
    result = ap_write_tools.prepare_payment_batch(
        ["INV-2291", "INV-2291A", "INV-2302", "INV-2317"]
    )

    assert set(result["included"]) == {"INV-2291", "INV-2291A"}
    assert result["total_cents"] == 480000  # two $2,400.00 invoices
    assert set(result["held"]) == {"INV-2302", "INV-2317"}


def test_bank_detail_change_is_always_a_hold():
    """The control that matters most: a vendor bank change can't be talked past."""
    result = ap_write_tools.prepare_payment_batch(["INV-2302"])
    assert result["included"] == []
    assert "changed bank details on 2026-09-27" in result["held"]["INV-2302"]


def test_missing_invoice_approval_is_a_hold():
    result = ap_write_tools.prepare_payment_batch(["INV-2317"])
    assert "no invoice approval on record" in result["held"]["INV-2317"]


def test_unknown_invoice_is_held_not_silently_dropped():
    result = ap_write_tools.prepare_payment_batch(["INV-9999"])
    assert result["included"] == []
    assert "not found" in result["held"]["INV-9999"]


def test_payment_batch_lands_pending_in_the_human_queue():
    result = ap_write_tools.prepare_payment_batch(["INV-2291"])
    bundle = store.get_bundle("sandbox")
    batch = next(a for a in bundle.approvals if a.id == result["approval_id"])
    assert batch.kind == "payment"
    assert batch.status == "pending"
    assert batch.verified is False


def test_human_can_then_release_the_batch_the_agent_prepared():
    """End to end: agent proposes, only the human path moves it off pending."""
    result = ap_write_tools.prepare_payment_batch(["INV-2291"])
    bundle = store.decide_approval("sandbox", result["approval_id"], "approved")
    released = next(a for a in bundle.approvals if a.id == result["approval_id"])
    assert released.status == "approved"


def test_store_refuses_a_pre_approved_approval():
    with pytest.raises(ValueError, match="pending"):
        store.append_approval(
            "sandbox",
            {
                "id": "EV-99",
                "agent": "ap",
                "kind": "evidence",
                "title": "t",
                "summary": "s",
                "verified": True,
                "status": "approved",
            },
        )


def test_write_tools_are_reachable_through_the_gateway_and_spend_budget():
    gateway = ToolGateway(budget=2)
    result = gateway.call("prepare_payment_batch", invoice_ids=["INV-2291"])
    assert result["included"] == ["INV-2291"]
    assert gateway.used == 1


def test_gateway_returns_a_rule_violation_as_a_correctable_error():
    gateway = ToolGateway()
    result = gateway.call("submit_finding", title="t", summary="s", status="substantiated", evidence=[])
    assert "rejected" in result["error"]
    assert gateway.used == 1  # a real attempt, so it costs budget


def test_duplicate_invoice_ids_never_double_payment_total():
    result = ap_write_tools.prepare_payment_batch(["INV-2291", "INV-2291"])
    assert result["included"] == ["INV-2291"]
    assert result["total_cents"] == 240000


def test_vendor_on_hold_is_not_paid(monkeypatch):
    vendor = ap_tools.get_vendor("V-08").model_copy(update={"status": "hold"})
    monkeypatch.setattr(ap_tools, "get_vendor", lambda *_: vendor)
    result = ap_write_tools.prepare_payment_batch(["INV-2291"])
    assert result["included"] == []
    assert "hold" in result["held"]["INV-2291"]


@pytest.mark.parametrize("action,record_type", [("rejected", "invoice"), ("approved", "purchase_order")])
def test_payment_requires_an_actual_invoice_approval(monkeypatch, action, record_type):
    approval = Approval(id="TEST", record_type=record_type, record_id="INV-2291", actor="Reviewer",
                        authority="Procurement", action=action, decided_at="2026-09-20T00:00:00")
    monkeypatch.setattr(ap_tools, "get_approvals_for_record", lambda *_: [approval])
    result = ap_write_tools.prepare_payment_batch(["INV-2291"])
    assert result["included"] == []
    assert "approval" in result["held"]["INV-2291"]


def test_later_rejection_blocks_an_earlier_approval(monkeypatch):
    approval = ap_tools.get_approvals_for_record("INV-2291")[0]
    rejected = approval.model_copy(update={"id": "rejected", "action": "rejected", "decided_at": "2026-10-01T00:00:00"})
    monkeypatch.setattr(ap_tools, "get_approvals_for_record", lambda *_: [approval, rejected])
    assert ap_write_tools.prepare_payment_batch(["INV-2291"])["included"] == []
