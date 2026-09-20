import pytest

from app import store
from app.agents import ap_write_tools, au_write_tools


@pytest.fixture(autouse=True)
def fresh_bundle():
    store.reset()
    yield
    store.reset()


def _file_a_finding() -> str:
    result = ap_write_tools.submit_finding(
        title="INV-2317 has no goods receipt",
        summary="Invoice matches PO-889 on amount, but no receipt is recorded.",
        status="substantiated",
        evidence=[{"label": "INV-2317", "kind": "record", "tone": "bad"}],
    )
    return result["finding_id"]


def test_accept_sets_verified_by_auditor():
    finding_id = _file_a_finding()
    result = au_write_tools.submit_review(
        finding_id, "accept", "Re-read PO-889 and confirmed the amount independently."
    )
    assert result["verified_by"] == "au"

    bundle = store.get_bundle("sandbox")
    filed = next(f for f in bundle.findings if f.id == finding_id)
    assert filed.verified_by == "au"


def test_auditor_can_read_exact_preparer_claim_without_changing_it():
    from app.agents.tool_gateway import AUDITOR_REGISTRY, ToolGateway
    finding_id = _file_a_finding()
    gateway = ToolGateway(registry=AUDITOR_REGISTRY)
    result = gateway.call("get_finding", finding_id=finding_id)
    assert result["finding"]["id"] == finding_id
    assert result["finding"]["verified_by"] is None
    assert result["finding"]["summary"] == "Invoice matches PO-889 on amount, but no receipt is recorded."
    assert "error" in gateway.call("get_finding", finding_id="D-99")


def test_reject_clears_verification_and_downgrades_status():
    finding_id = _file_a_finding()
    result = au_write_tools.submit_review(
        finding_id, "reject", "Re-checked receipts; the amount does not tie out."
    )
    assert result["verified_by"] is None
    assert result["status"] == "needs_evidence"


def test_needs_evidence_also_clears_verification():
    finding_id = _file_a_finding()
    result = au_write_tools.submit_review(
        finding_id, "needs_evidence", "Original PO document was not accessible to re-check."
    )
    assert result["verified_by"] is None
    assert result["status"] == "needs_evidence"


def test_review_without_evidence_note_is_rejected():
    finding_id = _file_a_finding()
    with pytest.raises(ValueError, match="re-check"):
        au_write_tools.submit_review(finding_id, "accept", "")


def test_unknown_finding_raises():
    with pytest.raises(KeyError):
        au_write_tools.submit_review("F-does-not-exist", "accept", "checked it")


def test_gateway_turns_unknown_finding_into_a_correctable_error_not_a_crash():
    """Regression: a live run had the auditor call submit_review with an
    invoice ID instead of a finding ID. store.apply_review's KeyError wasn't
    caught by ToolGateway.call, so it crashed the whole run — and, since this
    can happen inside a specialist spawned by assign_task, it crashed the
    CFO's run too. The gateway must turn this into an error the model can see
    and retry from, not an unhandled exception."""
    from app.agents.tool_gateway import AUDITOR_REGISTRY, ToolGateway

    gateway = ToolGateway(registry=AUDITOR_REGISTRY)
    result = gateway.call("submit_review", finding_id="INV-2302", decision="accept", evidence_note="checked it")
    assert "error" in result
    assert gateway.used == 1


def test_auditor_cannot_review_its_own_finding():
    store.append_finding(
        "sandbox",
        {
            "id": "F-99",
            "agent": "au",
            "title": "t",
            "summary": "s",
            "status": "substantiated",
            "amount_cents": None,
            "amount_note": None,
            "verified_by": None,
            "evidence": [{"label": "x", "kind": "record", "tone": "bad"}],
        },
    )
    with pytest.raises(ValueError, match="cannot review its own"):
        au_write_tools.submit_review("F-99", "accept", "checked it")
