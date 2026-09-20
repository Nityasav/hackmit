"""Where the graph stops and waits for a person.

An escalation that only *says* someone should look is a log line. This is the version
that holds: `interrupt()` pauses the run durably at the node that raised it, the
checkpointer keeps the state, and nothing continues until a decision arrives. No process
is held open, so a pause can outlast a restart, a deploy or a night.

Three properties this is built for:

**The pause survives the process.** State lives in the checkpointer, not in memory. The
thread is `(workspace, period, thread)`, so resuming is a lookup rather than a retry.

**The decision is a human's, and it becomes memory.** Resuming writes an approval
through `approvals.decide()`, which is the only writer of precedent. A later run is
offered what was decided and must re-check it against its own evidence.

**Nothing is decided by defaulting.** A pending escalation has no timeout that approves
it and no path that lets an agent resolve its own. It waits.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from .. import approvals, db
from ..agents.registry import AGENTS


def request_decision(*, ws: str, agent_id: str, thread_id: str, decision_id: str,
                     title: str, summary: str, reasons: tuple[str, ...],
                     event_id: str | None, citations: list[dict],
                     amount_cents: int | None = None) -> dict:
    """Record the proposal, then stop until a person answers it.

    The approval is written *before* the pause, so what the person is being asked is
    durable even if nothing ever resumes: an escalation that vanished with the process
    would be worse than one that never happened, because the run reported raising it.
    """
    spec = AGENTS[agent_id]
    # Derived from the thread and the agent, not from the decision that prompted it: a
    # resume re-runs this node, and an id that changed between the question and the
    # answer would leave the answer addressed to nothing.
    proposal_id = f"ESC-{thread_id}-{agent_id}"
    with db.connect() as connection:
        approvals.store(connection, ws, {
            "id": proposal_id, "agent": agent_id, "kind": "decision",
            "title": title, "summary": summary,
            "finding_id": decision_id, "task_id": agent_id, "run_id": thread_id,
            # An agent conclusion is not an independently reviewed one. A journal may
            # never be proposed from here, and `store` enforces that.
            "verified": False,
        })

    # Everything the person needs in order to answer, and nothing they would have to
    # go and look up. The payload is what the UI renders on the escalation queue.
    answer = interrupt({
        "kind": "decision_required",
        "approval_id": proposal_id,
        "workspace": ws,
        "agent": {"id": agent_id, "name": spec.name},
        "title": title,
        "summary": summary,
        "reasons": list(reasons),
        "event_id": event_id,
        "citations": citations,
        "amount_cents": amount_cents,
        "options": ["approved", "rejected"],
        "note": "Approving records your decision. It posts nothing, pays nothing and "
                "changes no external system.",
    })
    return _apply(ws, proposal_id, answer)


def _apply(ws: str, proposal_id: str, answer: Any) -> dict:
    """Record what the person chose, once the graph resumes with it.

    An approval row and a paused run are two halves of one question, and they can be
    answered from two screens. A person who decided it on the approvals page and then
    came back to the chat used to find the run stranded: `decide` refused the second
    call as already decided, the resume raised, and the graph never advanced past a
    question that had in fact been answered.

    So an already-decided approval is not an error here. The decision already on record
    is the person's, it is used as given, and the run continues. What is refused is a
    *different* answer to a question already settled — that is a real conflict and
    silently overwriting it would lose a decision somebody made.
    """
    decision = answer.get("decision") if isinstance(answer, dict) else answer
    if decision not in {"approved", "rejected"}:
        raise ValueError("A decision is either approved or rejected.")

    recorded = _recorded(ws, proposal_id)
    if recorded is None:
        # `decide` is the only path out of pending, and the only writer of precedent.
        approvals.decide(ws, proposal_id, decision)
        elsewhere = False
    else:
        if recorded != decision:
            raise ValueError(
                f"{proposal_id} was already {recorded} on the approvals page. Answering "
                f"it again as {decision} would overwrite a decision somebody made.")
        elsewhere = True

    return {
        "approval_id": proposal_id,
        "decision": decision,
        "decided_elsewhere": elsewhere,
        "note": ("Recorded as a human decision. Nothing was posted, paid or changed in "
                 "an external system." if not elsewhere else
                 "This was already decided on the approvals page. The run has been "
                 "continued with that decision; nothing was recorded twice."),
    }


def _recorded(ws: str, proposal_id: str) -> str | None:
    """The decision already on this approval, or None while it is still pending."""
    with db.connect() as connection:
        row = connection.execute(
            "SELECT status FROM approvals WHERE ws=? AND id=?", (ws, proposal_id)).fetchone()
    if row is None or row["status"] == "pending":
        return None
    return row["status"]


def _agent(agent_id: str) -> dict:
    """An agent as a screen needs it: the id to address, the name to show.

    A bare id renders as "B4" to someone who has no idea what B4 is.
    """
    spec = AGENTS.get(agent_id)
    return {"id": agent_id, "name": spec.name if spec else agent_id}


def pending(ws: str) -> list[dict]:
    """Escalations still waiting on someone, newest first."""
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT a.*, d.thread_id, d.confidence, d.evidence FROM approvals a"
            " LEFT JOIN agent_decisions d ON d.id = a.finding_id"
            " WHERE a.ws=? AND a.status='pending' AND a.id LIKE 'ESC-%'"
            " ORDER BY a.rowid DESC", (ws,)).fetchall()
    return [{
        "approval_id": row["id"],
        # The same shape the interrupt payload carries. These two described one thing in
        # two ways — an object here and a bare id there — so a screen built against
        # either broke on the other, and the type that was meant to describe both could
        # only be right about one.
        "agent": _agent(row["agent"]),
        "title": row["title"],
        "summary": row["summary"], "thread_id": row["thread_id"],
        "confidence": row["confidence"], "decision_id": row["finding_id"],
    } for row in rows]
