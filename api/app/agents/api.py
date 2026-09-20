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
from pydantic import BaseModel, Field

from .. import db, ingestion
from .budget import BudgetExceeded, DAY_CAP_CENTS, Meter, RUN_CAP_CENTS, spent_today
from .registry import AGENTS, children
from .runtime import AgentFailed, run_agent
from .tools import ScopeError

router = APIRouter(prefix="/api/workspaces/{ws}/agents", tags=["Agent organization"])


class RunRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=2000)
    #: Narrow the task to specific records. Empty means the agent's whole scope.
    record_keys: list[str] = Field(default_factory=list, max_length=50)
    event_ids: list[str] = Field(default_factory=list, max_length=50)
    #: Lower the run cap for this task. It can never raise it.
    cap_cents: int | None = Field(default=None, ge=1)


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

    try:
        run = await run_agent(
            ws, agent_id, body.objective, meter=meter, thread_id=thread_id,
            record_keys=tuple(body.record_keys), event_ids=tuple(body.event_ids))
    except BudgetExceeded as exc:
        # 402 is the honest status: the work stopped because it ran out of money, not
        # because anything was wrong with the request.
        raise HTTPException(402, {"code": "budget_exceeded", "message": str(exc),
                                  "spend": meter.snapshot()})
    except ScopeError as exc:
        raise HTTPException(403, {"code": "out_of_scope", "message": str(exc)})
    except AgentFailed as exc:
        raise HTTPException(409, {"code": "agent_failed", "message": str(exc),
                                  "spend": meter.snapshot()})

    return {"thread_id": thread_id, **run.as_dict(), "spend": meter.snapshot()}
