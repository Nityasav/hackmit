"""HTTP surface for the agent organization.

Replaces the standalone triage routes. Where triage was one agent reading a snapshot
alone, this dispatches any agent in the registry against a bounded task, inside one
run's budget, and records what it did.

Every response carries what it cost. A run that produces a conclusion nobody can price
is a run nobody can govern, so the number is part of the contract rather than a
diagnostic.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from typing import Literal

from pydantic import BaseModel, Field

from .. import db, ingestion
from . import activity
from .budget import BudgetExceeded, DAY_CAP_CENTS, Meter, RUN_CAP_CENTS, spent_today
from .registry import AGENTS, children
from .runtime import AgentFailed, run_agent
from .tools import ScopeError

router = APIRouter(prefix="/api/workspaces/{ws}/agents", tags=["Agent organization"])


@router.get("/activity")
def activity_events(ws: str, thread_id: str = ""):
    if not thread_id:
        return board(ws)
    import json
    ingestion.workspace_config(ws)
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT id,created_at,payload FROM events WHERE ws=? AND kind='agent.activity' "
            "AND (json_extract(payload, '$.thread_id')=? OR json_extract(payload, '$.thread_id') IN "
            "(SELECT run_id FROM conversations WHERE ws=? AND thread_id=?)) ORDER BY rowid LIMIT 2000",
            (ws, thread_id, ws, thread_id)).fetchall()
    return {"events": [dict(id=r["id"], at=r["created_at"], **json.loads(r["payload"])) for r in rows]}


class Decision(BaseModel):
    thread_id: str = Field(min_length=1, max_length=100)
    decision: Literal["approved", "rejected"]
    #: Which question is being answered. Several agents can pause in one run, and one
    #: answer applied to all of them would record a decision on questions nobody was
    #: shown. Omitting it is only safe when exactly one is outstanding.
    approval_id: str = Field(default="", max_length=120)


class RunRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=2000)
    #: Narrow the task to specific records. Empty means the agent's whole scope.
    record_keys: list[str] = Field(default_factory=list, max_length=50)
    event_ids: list[str] = Field(default_factory=list, max_length=50)
    #: Lower the run cap for this task. It can never raise it.
    cap_cents: int | None = Field(default=None, ge=1)


@router.post("/approvals/{approval_id}/revise")
async def revise(ws: str, approval_id: str, body: RunRequest):
    from .continuation import resolve
    if not body.objective.strip():
        raise HTTPException(422, "Enter revised instructions.")
    with db.connect() as connection:
        row = connection.execute("SELECT * FROM approvals WHERE ws=? AND id=?", (ws, approval_id)).fetchone()
    if not row or row["agent"] not in AGENTS:
        raise HTTPException(404, "No current agent for this approval.")
    if row["status"] == "pending":
        await resolve(ws, approval_id, "rejected")
    thread = db.uid("thread")
    with db.connect() as connection:
        db.event(connection, ws, "review.revised_instructions",
                 {"approval_id": approval_id, "agent": row["agent"], "instruction": body.objective, "thread_id": thread})
    try:
        run = await run_agent(ws, row["agent"], body.objective.strip(),
                              meter=Meter(run_cap_cents=min(body.cap_cents or RUN_CAP_CENTS, RUN_CAP_CENTS)),
                              thread_id=thread)
    except BudgetExceeded as exc:
        raise HTTPException(402, {"code": "budget_exceeded", "message": str(exc)})
    except (AgentFailed, ScopeError) as exc:
        raise HTTPException(422, str(exc))
    return {"thread_id": thread, **run.as_dict()}


@router.get("")
def organization(ws: str):
    """The agent tree, what each agent needs, and what is blocking it.

    Read straight from the registry, so this cannot describe an organization that
    differs from the one that would actually run.
    """
    ingestion.workspace_config(ws)
    view = ingestion.coverage(ws)
    blocked = view["blocked_agents"]
    labels = {r["id"]: r["label"] for r in view["requirements"]}
    with db.connect() as connection:
        today = spent_today(connection, ws)

    def node(spec):
        return {
            "id": spec.id, "name": spec.name, "tier": spec.tier, "parent": spec.parent,
            "charter": spec.charter, "model": spec.model,
            "uses_model_in_hot_path": spec.llm,
            "reads": list(spec.roles), "reviewer": spec.reviewer,
            "blocked_by": [labels.get(r, r) for r in blocked.get(spec.id, [])],
            "ready": not blocked.get(spec.id),
            "budget": {"model_calls": spec.budget.model_calls,
                       "tool_calls": spec.budget.tool_calls,
                       "usd_cents": spec.budget.usd_cents},
            "escalates_when": {"confidence_below": spec.escalate_when.confidence_below,
                               "amount_above_cents": spec.escalate_when.amount_above_cents,
                               "conditions": list(spec.escalate_when.on)},
            "children": [child.id for child in children(spec.id)],
        }

    return {
        "agents": [node(spec) for spec in AGENTS.values()],
        "spend": {"today_cents": today, "day_cap_cents": DAY_CAP_CENTS,
                  "run_cap_cents": RUN_CAP_CENTS},
        "note": "An agent is ready when the data it declared has been supplied. Ready "
                "does not mean its conclusions are verified.",
    }


def board(ws: str):
    """What every agent is doing right now, and what each one did.

    Polled by the board. It is a read of `agent_tasks`, which the runtime writes as the
    work happens — so a task appears when it is delegated, its steps appear as its tool
    calls land, and its card closes when it ends. Nothing here is a projection of what a
    model claimed about itself.
    """
    ingestion.workspace_config(ws)
    with db.connect() as connection:
        today = spent_today(connection, ws)
    return {**activity.live(ws),
            "spend": {"today_cents": today, "day_cap_cents": DAY_CAP_CENTS,
                      "run_cap_cents": RUN_CAP_CENTS}}


@router.get("/{agent_id}/decisions")
def decisions(ws: str, agent_id: str, limit: int = 50):
    """What this agent has decided in this workspace, newest first."""
    if agent_id not in AGENTS:
        raise HTTPException(404, "No such agent.")
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT * FROM agent_decisions WHERE ws=? AND agent=? ORDER BY rowid DESC LIMIT ?",
            (ws, agent_id, min(limit, 200))).fetchall()
    return {"agent_id": agent_id, "decisions": [dict(row) for row in rows]}


@router.get("/{agent_id}/insights")
def insights(ws: str, agent_id: str):
    """Current deterministic figures, not model prose or an approval."""
    from .tools import Toolbox
    if agent_id not in {"A2", "C3"}:
        raise HTTPException(404, "No chart for this agent.")
    coverage = ingestion.coverage(ws)
    if coverage["blocked_agents"].get(agent_id):
        raise HTTPException(409, "Supply the required records before calculating this view.")
    config = ingestion.workspace_config(ws)
    box = Toolbox(ws, AGENTS[agent_id], Meter(), ingestion.financial_records(ws)["records"],
                  config, coverage["snapshot"]["id"], "read-only")
    result = box.age_receivables() if agent_id == "A2" else box.decompose_variance()
    return {"snapshot_id": coverage["snapshot"]["id"], "agent_id": agent_id,
            "currency": config["currency"], "data": result}


@router.post("/{agent_id}/runs", status_code=201)
async def start(ws: str, agent_id: str, body: RunRequest, request: Request):
    """Run one agent against a bounded task. Paid work; the cost is in the response."""
    if agent_id not in AGENTS:
        raise HTTPException(404, "No such agent.")
    spec = AGENTS[agent_id]
    if spec.tier == "orchestrator":
        raise HTTPException(
            409, "The orchestrator is driven from the Investigation chat, not started directly.")

    # A caller may tighten the cap but never loosen it: the configured ceiling is the
    # ceiling, and a request that asks for more is asking the wrong component.
    cap = min(body.cap_cents or RUN_CAP_CENTS, RUN_CAP_CENTS)
    meter = Meter(run_cap_cents=cap)
    thread_id = db.uid("thread")
    from .activity import emit
    emit(ws, thread_id, agent_id, "started", body.objective)
    try:
        run = await run_agent(
            ws, agent_id, body.objective, meter=meter, thread_id=thread_id,
            record_keys=tuple(body.record_keys), event_ids=tuple(body.event_ids))
    except BudgetExceeded as exc:
        emit(ws, thread_id, agent_id, "blocked", str(exc))
        # 402 is the honest status: the work stopped because it ran out of money, not
        # because anything was wrong with the request.
        raise HTTPException(402, {"code": "budget_exceeded", "message": str(exc),
                                  "spend": meter.snapshot()})
    except ScopeError as exc:
        emit(ws, thread_id, agent_id, "blocked", str(exc))
        raise HTTPException(403, {"code": "out_of_scope", "message": str(exc)})
    except AgentFailed as exc:
        emit(ws, thread_id, agent_id, "failed", str(exc))
        raise HTTPException(409, {"code": "agent_failed", "message": str(exc),
                                  "spend": meter.snapshot()})

    emit(ws, thread_id, agent_id, "needs_review" if run.escalated else "completed", run.result.summary if run.result else "Task completed.")
    return {"thread_id": thread_id, **run.as_dict(), "spend": meter.snapshot()}


@router.get("/escalations")
def escalations(ws: str):
    """What is waiting on a person, and what each run stopped to ask.

    A paused run is not a failed one and not a finished one. It is a question, and until
    it is answered nothing beyond it has happened.
    """
    from ..graph import pending

    waiting = pending(ws)
    return {
        "escalations": waiting,
        "count": len(waiting),
        "note": "Each of these paused a run. Deciding one resumes it; nothing is posted, "
                "paid or changed in an external system either way.",
    }


@router.post("/escalations/decide")
async def decide_escalation(ws: str, body: Decision):
    """Answer a paused run and let it continue.

    The decision is recorded through `approvals.decide()`, which is the only writer of
    precedent — so answering this is also what teaches the next run what you decided.
    """
    from ..graph import resume_investigation

    if body.approval_id:
        with db.connect() as connection:
            proposal = connection.execute("SELECT run_id FROM approvals WHERE ws=? AND id=?", (ws, body.approval_id)).fetchone()
            conversation = connection.execute("SELECT 1 FROM conversations WHERE ws=? AND thread_id=? AND run_id=?", (ws, body.thread_id, proposal["run_id"] if proposal else "")).fetchone()
        if not proposal or (proposal["run_id"] != body.thread_id and not conversation):
            raise HTTPException(404, "Approval not found in this run.")
        from .continuation import resolve
        return await resolve(ws, body.approval_id, body.decision)

    try:
        outcome = await resume_investigation(ws, body.thread_id, body.decision,
                                             approval_id=body.approval_id or None)
    except BudgetExceeded as exc:
        raise HTTPException(402, {"code": "budget_exceeded", "message": str(exc)})
    except KeyError as exc:
        # "No paused run" is true and useless. The usual cause is a question that has
        # already been answered — from the other screen, or from a card left on an
        # older message — and a person reading the literal message has no idea whether
        # their decision landed.
        settled = _already_decided(ws, body.approval_id)
        if settled:
            raise HTTPException(409, {
                "code": "already_decided",
                "message": f"That question was already {settled}, and the run has moved "
                           "past it. Nothing was lost and nothing needs doing again.",
                "decision": settled})
        raise HTTPException(404, {"code": "no_paused_run", "message": str(exc)})
    except ValueError as exc:
        # Several questions are waiting and the answer did not say which. Refused rather
        # than guessed: applying it to the wrong one records a decision the person never
        # made, against evidence they never saw.
        raise HTTPException(409, {"code": "ambiguous_decision", "message": str(exc)})
    return outcome


def _already_decided(ws: str, approval_id: str) -> str | None:
    """What a person decided about this question, if they already have."""
    if not approval_id:
        return None
    with db.connect() as connection:
        row = connection.execute(
            "SELECT status FROM approvals WHERE ws=? AND id=?", (ws, approval_id)).fetchone()
    if row is None or row["status"] == "pending":
        return None
    return row["status"]


@router.get("/timeline")
def timeline(ws: str, limit: int = 100):
    """Every economic event in this workspace, newest first.

    One row per transaction rather than per document, which is the point of the event
    identity: the invoice, the receipt, the payment and the journal entries are views of
    one thing, and a timeline that listed each separately would report one purchase four
    times.
    """
    from .. import events

    ingestion.workspace_config(ws)
    with db.connect() as connection:
        rows = events.timeline(connection, ws, limit=min(limit, 500))
    return {
        "events": rows, "count": len(rows),
        "note": "One row per economic event. An event carries whatever documents named "
                "it, which is not a claim that every document that should exist does.",
    }


@router.get("/timeline/{event_id}")
def event(ws: str, event_id: str):
    """Everything that carries one event id: records, decisions and links."""
    from .. import events

    ingestion.workspace_config(ws)
    with db.connect() as connection:
        found = events.view(connection, ws, event_id)
        if found is None:
            raise HTTPException(404, "No such event in this workspace.")
        decisions = [dict(row) for row in connection.execute(
            "SELECT id, agent, action, summary, confidence, escalated, created_at"
            " FROM agent_decisions WHERE ws=? AND event_id=? ORDER BY rowid", (ws, event_id))]
        links = [dict(row) for row in connection.execute(
            "SELECT from_type, from_id, to_type, to_id, kind, method, confidence"
            " FROM links WHERE ws=? AND event_id=? ORDER BY rowid", (ws, event_id))]
    return {**found, "decisions": decisions, "links": links}
