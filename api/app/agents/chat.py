"""The conversation that drives the organization.

One box. A person says what they want looked at, the orchestrator routes it to the domains
it touches, and what comes back is the run — the plan, what each agent concluded, what it
cost, and anything that stopped for a person.

## Why the conversation is stored, and what is stored

Every turn is written to `conversations` before the run starts and updated when it ends, so
a run that crashes, times out or is still going leaves a question on the record rather than
disappearing. The reply is assembled from the run's own state rather than written by a
model: there is no model in this module at all. The orchestrator's model budget goes on
routing and synthesis inside the graph, and putting a second one here would mean a person
reads prose that nothing checked.

## What a turn is not

It is not a chat with a model that has opinions about your books. Every sentence in a reply
is either a count of something in the run or a line the agents themselves recorded, and a
turn that produced no findings says so instead of filling the space.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import db, ingestion
from .budget import BudgetExceeded, Meter, RUN_CAP_CENTS
from .registry import AGENTS
from .runtime import AgentFailed
from .tools import ScopeError

router = APIRouter(prefix="/api/workspaces/{ws}", tags=["Orchestrator chat"])

MAX_TURNS = 100


class Message(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    #: Continue an existing exchange. A new one starts its own thread.
    thread_id: str = Field(default="", max_length=100)
    #: Lower the run cap for this turn. It can never raise it.
    cap_cents: int | None = Field(default=None, ge=1)


def _record(connection, ws: str, turn: dict) -> None:
    connection.execute(
        "INSERT INTO conversations (id, ws, thread_id, role, body, status, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (turn["id"], ws, turn["thread_id"], turn["role"], db.encode(turn["body"]),
         turn["status"], turn["created_at"]))


def _finish(connection, ws: str, turn_id: str, body: dict, status: str) -> None:
    connection.execute(
        "UPDATE conversations SET body=?, status=? WHERE ws=? AND id=?",
        (db.encode(body), status, ws, turn_id))


def reply_for(run: dict) -> dict:
    """What to say back, counted from the run rather than composed about it.

    Deliberately flat prose over deliberately exact numbers. The temptation here is a
    model writing a friendly summary; the problem with one is that a person then reads a
    sentence no check stands behind, in the same typeface as the ones that are.
    """
    findings = run.get("findings") or []
    # `waiting_on_you` is what the graph calls it; `escalations` is what the browser
    # reads. Translated in one place rather than letting both names travel.
    waiting = run.get("waiting_on_you") or []
    routed = [AGENTS[worker].name for worker in run.get("plan") or [] if worker in AGENTS]
    unresolved = run.get("unresolved") or []

    if not routed:
        headline = ("Nothing in that was routed to a domain I have wired, so no agent was "
                    "asked anything.")
    else:
        headline = "Routed to " + ", ".join(routed) + "."

    lines = [headline]
    if findings:
        lines.append(f"{len(findings)} conclusion(s) recorded"
                     + (f", {len(waiting)} waiting on you." if waiting else "."))
    else:
        lines.append("No agent reached a conclusion. That is not a clean result; it means "
                     "nothing was concluded.")
    lines += unresolved
    if waiting:
        lines.append("Answer the question(s) below and the run continues from where it "
                     "stopped. Nothing beyond that point has happened yet.")

    return {
        "text": " ".join(lines),
        "plan": run.get("plan") or [],
        "routed_to": routed,
        "findings": findings,
        "escalations": waiting,
        "unresolved": unresolved,
        "status": run.get("status"),
        "spend": run.get("spend"),
        "thread_id": run.get("thread_id"),
        "note": "Every sentence above is a count of what the run produced or a line an "
                "agent recorded. Nothing in this reply was written by a model.",
    }


@router.get("/chat")
def history(ws: str, thread_id: str = "", limit: int = MAX_TURNS):
    """The exchange so far, oldest first, so a reader follows it in order."""
    ingestion.workspace_config(ws)
    with db.connect() as connection:
        if thread_id:
            rows = connection.execute(
                "SELECT * FROM conversations WHERE ws=? AND thread_id=? ORDER BY rowid"
                " LIMIT ?", (ws, thread_id, min(limit, MAX_TURNS))).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM conversations WHERE ws=? ORDER BY rowid LIMIT ?",
                (ws, min(limit, MAX_TURNS))).fetchall()
    return {
        "turns": [{"id": r["id"], "thread_id": r["thread_id"], "role": r["role"],
                   "status": r["status"], "created_at": r["created_at"],
                   "body": json.loads(r["body"] or "{}")} for r in rows],
        "note": "Turns are recorded as they happen. A turn that stopped or failed stays "
                "on the record rather than disappearing.",
    }


@router.post("/chat", status_code=201)
async def talk(ws: str, body: Message):
    """Say something to the orchestrator. Paid work; the cost comes back with the reply."""
    from ..graph import run_investigation

    ingestion.workspace_config(ws)
    thread_id = body.thread_id or db.uid("thread")
    now = db.now()

    asked = {"id": db.uid("turn"), "thread_id": thread_id, "role": "person",
             "body": {"text": body.message}, "status": "sent", "created_at": now}
    answer_id = db.uid("turn")
    with db.connect() as connection:
        _record(connection, ws, asked)
        # Written before the run, not after. A run that crashes or times out must still
        # leave the question visible; a turn that only appears once it succeeds makes a
        # failure look like something the person never asked.
        _record(connection, ws, {
            "id": answer_id, "thread_id": thread_id, "role": "orchestrator",
            "body": {"text": "Working on it."}, "status": "running", "created_at": now})

    meter = Meter(run_cap_cents=min(body.cap_cents or RUN_CAP_CENTS, RUN_CAP_CENTS))
    try:
        run = await run_investigation(ws, body.message, thread_id=thread_id,
                                      cap_cents=meter.run_cap_cents)
    except BudgetExceeded as exc:
        return _failed(ws, answer_id, thread_id, str(exc), 402, "budget_exceeded")
    except ScopeError as exc:
        return _failed(ws, answer_id, thread_id, str(exc), 403, "out_of_scope")
    except AgentFailed as exc:
        return _failed(ws, answer_id, thread_id, str(exc), 409, "agent_failed")

    reply = reply_for(run)
    with db.connect() as connection:
        _finish(connection, ws, answer_id, reply,
                "waiting_on_you" if reply["escalations"] else "done")
    return {"thread_id": thread_id, "turn_id": answer_id, "reply": reply, "run": run}


def _failed(ws: str, turn_id: str, thread_id: str, message: str, status: int, code: str):
    """Record why the turn stopped, then say so with the right status.

    The failure is written to the conversation first. A person who asked a question and
    got an error dialog should still find the question, and what became of it, on the
    record afterwards.
    """
    body = {"text": message, "code": code, "findings": [], "escalations": []}
    with db.connect() as connection:
        _finish(connection, ws, turn_id, body, "failed")
    raise HTTPException(status, {"code": code, "message": message,
                                 "thread_id": thread_id, "turn_id": turn_id})
