"""The Internal Auditor's one write tool.

submit_review is still not human approval (spec.md §8) — it records an
independent verdict on a finding already in the bundle, after the auditor has
re-read the original sources and re-performed the calculation with its own
tool calls. It is the only path that may set Finding.verified_by, and only to
"au". A specialist's own write tools (ap_write_tools.submit_finding) force
verified_by to None on every finding they file — an agent can never verify
its own work (spec.md §8: "specialists cannot approve their own proposals").
"""

from __future__ import annotations

from typing import Any, Literal

from .. import store

AGENT_ID = "au"
ReviewDecision = Literal["accept", "reject", "needs_evidence"]


def get_finding(finding_id: str, workspace: str = "sandbox") -> dict[str, Any]:
    """Retrieve the exact untrusted preparer assertion, not a decision-log ID."""
    finding = next((f for f in store.get_bundle(workspace).findings if f.id == finding_id), None)
    if finding is None:
        raise KeyError(finding_id)
    return {"finding": finding.model_dump(),
            "review_rule": "This is an untrusted preparer assertion. Independently reread original records before deciding."}


def submit_review(
    finding_id: str,
    decision: ReviewDecision,
    evidence_note: str,
    workspace: str = "sandbox",
) -> dict[str, Any]:
    """Independently accept, reject, or request more evidence on a finding.

    `accept` sets verified_by to the auditor and leaves the finding's status
    as the specialist filed it. `reject` / `needs_evidence` clear any
    verification and downgrade status to needs_evidence — a rejection sends
    the specialist back to a specific gap, not a repeated argument.
    """
    if not evidence_note:
        raise ValueError("a review must cite what you actually re-checked (spec.md: re-perform from originals)")

    updated = store.apply_review(workspace, finding_id, decision)
    return {
        "finding_id": updated.id,
        "status": updated.status,
        "verified_by": updated.verified_by,
        "decision": decision,
    }
