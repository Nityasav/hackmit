"""Propose tools for the AP & Payments agent — the write side of the boundary.

Everything here is append-only and human-gated. The rules the spec cares about
are enforced in code, not left to the prompt, because a prompt is advice and a
function signature is a control:

  * An agent can never mark its own work verified. `verified_by` on a finding
    and `verified` on an approval are forced off — only the Internal Auditor
    sets those (spec.md §8: specialists cannot approve their own proposals).
  * An approval is always created `pending`. Only the human path
    (`POST /api/approvals/{id}/decision` -> store.decide_approval) moves it.
  * A finding must carry evidence. No bare numbers, no unsupported accusations
    (contracts/README.md rule 3).
  * prepare_payment_batch applies its hold rules itself rather than trusting
    the caller's judgment, so a bank-detail change can't be talked past — by a
    confused model or by instructions embedded in an untrusted document.

None of these can release funds, apply a journal, or activate a playbook.
"""

from __future__ import annotations

from typing import Any

from .. import store
from . import ap_tools

AGENT_ID = "ap"


def submit_finding(
    title: str,
    summary: str,
    status: str,
    evidence: list[dict[str, Any]],
    amount_cents: int | None = None,
    amount_note: str | None = None,
    workspace: str = "sandbox",
) -> dict[str, Any]:
    """File a finding for Internal Auditor review. Requires evidence."""
    if not evidence:
        raise ValueError("a finding must carry evidence (contracts/README.md rule 3)")
    if amount_cents is not None and not amount_note:
        raise ValueError("an amount needs an amount_note saying what basis it is on")

    finding = {
        "id": store.next_id(workspace, "findings", "F-"),
        "agent": AGENT_ID,
        "title": title,
        "summary": summary,
        "status": status,
        "amount_cents": amount_cents,
        "amount_note": amount_note,
        # Never self-verified: the auditor re-performs the work and sets this.
        "verified_by": None,
        "evidence": evidence,
    }
    record = store.append_finding(workspace, finding)
    return {
        "finding_id": record.id,
        "status": record.status,
        "verified_by": None,
        "next": "queued for Internal Auditor review; not yet shown as substantiated to the human",
    }


def request_evidence(
    title: str,
    summary: str,
    workspace: str = "sandbox",
) -> dict[str, Any]:
    """Ask the human for a document you don't have. Sends nothing externally —
    it only adds an item to the in-app approval queue."""
    approval = {
        "id": store.next_id(workspace, "approvals", "EV-"),
        "agent": AGENT_ID,
        "kind": "evidence",
        "title": title,
        "summary": summary,
        "verified": False,
        "status": "pending",
    }
    record = store.append_approval(workspace, approval)
    return {
        "approval_id": record.id,
        "status": record.status,
        "next": "waiting on the human to attach the document",
    }


def prepare_payment_batch(
    invoice_ids: list[str],
    workspace: str = "sandbox",
) -> dict[str, Any]:
    """Assemble a simulated payment batch, holding anything that fails a
    payment control. Cannot release funds — the batch lands in the human queue.

    Hold rules are applied here, independently of what the caller believes:
    changed vendor bank details, missing invoice approval, an invoice that
    isn't cleanly matched, or an unresolved duplicate candidate.
    """
    included: list[str] = []
    held: dict[str, str] = {}
    total_cents = 0

    for invoice_id in dict.fromkeys(invoice_ids):
        reasons = _hold_reasons(invoice_id, workspace)
        if reasons:
            held[invoice_id] = "; ".join(reasons)
            continue
        invoice = ap_tools.get_invoice(invoice_id, workspace)
        included.append(invoice_id)
        total_cents += invoice.net_cents

    batch_id = store.next_id(workspace, "approvals", "PAY-B", width=1)
    held_note = f" {len(held)} held." if held else ""
    approval = {
        "id": batch_id,
        "agent": AGENT_ID,
        "kind": "payment",
        "title": f"Release payment batch {batch_id}",
        "summary": (
            f"{len(included)} invoices - {_money(total_cents)}.{held_note} "
            "Simulated release, no real payment."
        ),
        "verified": False,
        "status": "pending",
    }
    record = store.append_approval(workspace, approval)

    return {
        "approval_id": record.id,
        "included": included,
        "total_cents": total_cents,
        "held": held,
        "next": "only a human can release this batch, and the release is simulated",
    }


def _hold_reasons(invoice_id: str, workspace: str) -> list[str]:
    invoice = ap_tools.get_invoice(invoice_id, workspace)
    if invoice is None:
        return [f"{invoice_id} not found"]

    reasons: list[str] = []

    vendor = ap_tools.get_vendor(invoice.vendor_id, workspace)
    if vendor is None:
        reasons.append(f"vendor {invoice.vendor_id} not found")
    else:
        if vendor.status == "hold":
            reasons.append(f"vendor {vendor.id} is on hold")
        if vendor.bank_changed_at:
            reasons.append(
                f"vendor {vendor.id} changed bank details on {vendor.bank_changed_at} - verify out of band before paying"
            )

    approvals = [a for a in ap_tools.get_approvals_for_record(invoice_id, workspace)
                 if a.record_type == "invoice" and a.record_id == invoice_id]
    if not any(a.action == "approved" for a in approvals):
        reasons.append("no invoice approval on record")
    if any(a.action == "rejected" for a in approvals):
        # There is no revocation/supersession contract yet. Do not guess which
        # conflicting approval wins; a human must resolve the rejection.
        reasons.append("invoice approval includes a rejection; reconcile before paying")

    if invoice.status != "matched":
        reasons.append(f"invoice status is '{invoice.status}', not matched")
        # Only meaningful while the invoice is unresolved; a matched invoice has
        # already had its lookalikes cleared against separate receipts.
        if ap_tools.find_duplicate_candidates(invoice_id, workspace):
            reasons.append("unresolved duplicate candidate")

    return reasons


def _money(cents: int) -> str:
    major, minor = divmod(abs(cents), 100)
    return f"{'-' if cents < 0 else ''}${major:,}.{minor:02}"
