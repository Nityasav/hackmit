import pytest

from app import store


@pytest.fixture(autouse=True)
def fresh_bundle():
    store.reset()
    yield
    store.reset()


VALID_DECISION = {
    "id": "D-99",
    "run": "run-test",
    "time": "14:06",
    "agent": "ap",
    "action": "Investigated INV-2302",
    "summary": "Checked vendor, PO, and approvals.",
    "tags": [],
    "when": {
        "run": "run-test",
        "step": "3 of 12 tool calls",
        "started": "14:06:00",
        "finished": "14:06:05 (5s)",
        "trigger": "Should INV-2302 be paid?",
    },
    "how": [{"tool": "get_invoice", "input": "invoice_id='INV-2302'", "output": "Invoice INV-2302"}],
    "why": "Vendor bank details changed recently.",
    "alternatives": [{"option": "Pay it", "reason": "amount matches PO", "chosen": False}],
    "memory_checks": [],
    "outcome": "Held pending verification.",
}


def test_append_decision_lands_in_the_bundle():
    store.append_decision("sandbox", VALID_DECISION)
    bundle = store.get_bundle("sandbox")
    assert any(d.id == "D-99" for d in bundle.decisions)


def test_append_decision_validates_shape():
    bad = {**VALID_DECISION, "when": "not a dict"}
    with pytest.raises(Exception):
        store.append_decision("sandbox", bad)


def test_next_id_continues_decision_sequence():
    # The sandbox fixture ships D-41, D-42.
    assert store.next_id("sandbox", "decisions", "D-") == "D-43"
    store.append_decision("sandbox", {**VALID_DECISION, "id": "D-43"})
    assert store.next_id("sandbox", "decisions", "D-") == "D-44"


def test_apply_review_accept_sets_verified_by():
    store.append_finding(
        "sandbox",
        {
            "id": "F-50",
            "agent": "ap",
            "title": "t",
            "summary": "s",
            "status": "substantiated",
            "amount_cents": None,
            "amount_note": None,
            "verified_by": None,
            "evidence": [{"label": "x", "kind": "record", "tone": "bad"}],
        },
    )
    updated = store.apply_review("sandbox", "F-50", "accept")
    assert updated.verified_by == "au"


def test_apply_review_unknown_finding_raises_keyerror():
    with pytest.raises(KeyError):
        store.apply_review("sandbox", "F-nope", "accept")
