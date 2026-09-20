"""What the agents are doing, written while they do it.

`agent_decisions` is the trail of what was *concluded*. It can only be written once a
task is over, so a board built from it shows finished work and nothing else — which is
exactly what the task board was doing: every card `done`, every one at 100%, every one
reporting zero tool calls, because those fields had nowhere real to come from.

This module owns the other half. One row per delegated task:

- **opened** before the model is called, so a task appears the moment it exists,
- **appended to** on every tool call, from the one place every tool call passes through,
- **closed** when the task ends, carrying the decision it produced.

Every field on the board is therefore something the run did, not something a model said
about itself. A task that stops recording is reported as stalled rather than left
spinning: a card that claims to be working when nothing is running is worse than no card.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from .. import db
from .registry import AGENTS

#: A working task whose last step is older than this is no longer believable. The
#: process that owned it is gone — a restart, a crash, a closed browser mid-run — and
#: the row would otherwise sit in `working` forever with a clock ticking against it.
STALL_AFTER = timedelta(minutes=15)

#: Columns the board renders, in the order work moves through them.
STATES = ("queued", "working", "auditor_review", "needs_you", "done", "failed")


def _steps(row) -> list[dict]:
    try:
        return json.loads(row["steps"] or "[]")
    except (TypeError, ValueError):
        return []


def _json(value, fallback):
    try:
        return json.loads(value) if value else fallback
    except (TypeError, ValueError):
        return fallback


def _parsed(value: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #

def seed(ws: str, thread_id: str, agent_ids, objective: str) -> None:
    """Put every agent this run intends to ask into `queued`.

    Delegation that is only visible once it finishes is indistinguishable from
    delegation that never happened, so the plan is written down before any of it runs.
    """
    with db.connect() as connection:
        for agent_id in agent_ids:
            if agent_id not in AGENTS:
                continue
            spec = AGENTS[agent_id]
            existing = connection.execute(
                "SELECT id FROM agent_tasks WHERE ws=? AND thread_id=? AND agent=?",
                (ws, thread_id, agent_id)).fetchone()
            if existing:
                continue
            connection.execute(
                "INSERT INTO agent_tasks (id, ws, thread_id, agent, parent_agent, objective,"
                " state, steps, tool_budget, model_budget, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (db.uid("task"), ws, thread_id, agent_id, spec.parent, objective[:2000],
                 "queued", "[]", spec.budget.tool_calls, spec.budget.model_calls,
                 db.now(), db.now()))


def start(ws: str, thread_id: str, agent_id: str, objective: str) -> str:
    """Open this agent's task, or take over the queued row the plan already wrote."""
    spec = AGENTS[agent_id]
    now = db.now()
    with db.connect() as connection:
        row = connection.execute(
            "SELECT id FROM agent_tasks WHERE ws=? AND thread_id=? AND agent=? AND state='queued'",
            (ws, thread_id, agent_id)).fetchone()
        task_id = row["id"] if row else db.uid("task")
        if row:
            connection.execute(
                "UPDATE agent_tasks SET state='working', objective=?, started_at=?,"
                " updated_at=? WHERE id=?",
                (objective[:2000], now, now, task_id))
        else:
            connection.execute(
                "INSERT INTO agent_tasks (id, ws, thread_id, agent, parent_agent, objective,"
                " state, steps, tool_budget, model_budget, created_at, started_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (task_id, ws, thread_id, agent_id, spec.parent, objective[:2000],
                 "working", "[]", spec.budget.tool_calls, spec.budget.model_calls,
                 now, now, now))
    return task_id


def step(task_id: str | None, title: str, *, detail: str = "", state: str = "done",
         counts_as_tool: bool = False, counts_as_model: bool = False) -> None:
    """Append one thing this task did. Never raises into the run.

    A failed write here must not take down the work it was only describing, so every
    error is swallowed. The consequence — a step missing from the board — is visible;
    a run killed by its own telemetry would not be.
    """
    if not task_id:
        return
    try:
        with db.connect() as connection:
            row = connection.execute(
                "SELECT steps, tool_calls, model_calls FROM agent_tasks WHERE id=?",
                (task_id,)).fetchone()
            if row is None:
                return
            steps = _steps(row)
            steps.append({"title": title[:200], "detail": detail[:400] or None,
                          "state": state, "memory": False,
                          "at": db.now()})
            connection.execute(
                "UPDATE agent_tasks SET steps=?, tool_calls=?, model_calls=?, updated_at=?"
                " WHERE id=?",
                (db.encode(steps[-60:]),
                 row["tool_calls"] + (1 if counts_as_tool else 0),
                 row["model_calls"] + (1 if counts_as_model else 0),
                 db.now(), task_id))
    except Exception:  # noqa: BLE001 - telemetry must never fail the work
        return


def finish(task_id: str | None, *, state: str, summary: str = "", confidence: int | None = None,
           decision_id: str | None = None, escalated: bool = False,
           reasons: tuple[str, ...] = (), cost_cents: int = 0,
           tool_calls: int | None = None, model_calls: int | None = None,
           error: str | None = None, result: dict | None = None) -> None:
    """Close the task with what it actually produced."""
    if not task_id:
        return
    now = db.now()
    try:
        with db.connect() as connection:
            row = connection.execute(
                "SELECT tool_calls, model_calls FROM agent_tasks WHERE id=?",
                (task_id,)).fetchone()
            if row is None:
                return
            connection.execute(
                "UPDATE agent_tasks SET state=?, summary=?, confidence=?, decision_id=?,"
                " escalated=?, escalation_reasons=?, cost_cents=?, tool_calls=?,"
                " model_calls=?, error=?, result=?, updated_at=?, finished_at=? WHERE id=?",
                (state, summary[:600], confidence, decision_id, int(escalated),
                 db.encode(list(reasons)), cost_cents,
                 # The meter is authoritative when the run hands it over: it counted
                 # every charge, including the ones that raised before a step was written.
                 row["tool_calls"] if tool_calls is None else max(tool_calls, row["tool_calls"]),
                 row["model_calls"] if model_calls is None else max(model_calls, row["model_calls"]),
                 error, db.encode(result or {}), now, now, task_id))
    except Exception:  # noqa: BLE001
        return


def mark(task_id: str | None, state: str) -> None:
    """Move a card without closing it — a finished task waiting on its reviewer."""
    if not task_id:
        return
    try:
        with db.connect() as connection:
            connection.execute("UPDATE agent_tasks SET state=?, updated_at=? WHERE id=?",
                               (state, db.now(), task_id))
    except Exception:  # noqa: BLE001
        return


def attach_review(task_id: str | None, review: dict) -> None:
    """Record what the independent reviewer concluded about this task."""
    if not task_id:
        return
    try:
        with db.connect() as connection:
            connection.execute("UPDATE agent_tasks SET review=?, updated_at=? WHERE id=?",
                               (db.encode(review), db.now(), task_id))
    except Exception:  # noqa: BLE001
        return


def resolve(ws: str, *, decision: str, by: str,
            decision_id: str | None = None, approval_id: str | None = None) -> list[str]:
    """Close every card waiting on this question, now that it has an answer.

    Nothing did this, so a card went on saying "waiting on your decision" after the
    decision was made: the approval row moved to `approved` and the board — the one
    screen that shows what is outstanding — never heard about it.

    Returns the threads whose runs were paused on it, so the caller can start them
    again. Recording the answer and acting on it are two different things and only one
    of them belongs in here.
    """
    if not decision_id and not approval_id:
        return []
    answer = db.encode({"decision": decision, "by": by, "at": db.now()})
    threads: list[str] = []
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT id, thread_id FROM agent_tasks WHERE ws=? AND (decision_id=? OR approval_id=?)",
            (ws, decision_id or "", approval_id or "")).fetchall()
        for row in rows:
            connection.execute(
                "UPDATE agent_tasks SET state='done', resolution=?, updated_at=?,"
                " finished_at=COALESCE(finished_at, ?) WHERE id=?",
                (answer, db.now(), db.now(), row["id"]))
            if row["thread_id"]:
                threads.append(row["thread_id"])
    return sorted(set(threads))


def attach_approval(ws: str, decision_id: str, approval_id: str) -> None:
    """Point the card at the question a person has to answer."""
    try:
        with db.connect() as connection:
            connection.execute(
                "UPDATE agent_tasks SET approval_id=?, updated_at=? WHERE ws=? AND decision_id=?",
                (approval_id, db.now(), ws, decision_id))
    except Exception:  # noqa: BLE001
        return


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #

def _progress(row, state: str) -> int:
    """How far along, from what was spent — never from a model's own estimate."""
    if state in {"done", "needs_you"}:
        return 100
    if state == "queued":
        return 0
    budget = row["tool_budget"] or AGENTS[row["agent"]].budget.tool_calls
    if not budget:
        return 5
    # Capped below 100 on purpose: a task that is still working has not finished, and a
    # full bar that then keeps moving is a lie the card tells for as long as it runs.
    return max(5, min(90, round(row["tool_calls"] / budget * 90)))


def _stalled(row, state: str, now: datetime) -> bool:
    if state not in {"working", "queued"}:
        return False
    updated = _parsed(row["updated_at"])
    return updated is not None and now - updated > STALL_AFTER


def card(row, now: datetime | None = None) -> dict:
    """One task, in the shape the board renders."""
    now = now or datetime.now(timezone.utc)
    agent = row["agent"] if row["agent"] in AGENTS else "orchestrator"
    state = row["state"]
    stalled = _stalled(row, state, now)
    if stalled:
        state = "failed"
    steps = [{"title": s.get("title", ""), "detail": s.get("detail"),
              "state": s.get("state", "done"), "memory": bool(s.get("memory")),
              "at": s.get("at")}
             for s in _steps(row)]
    reasons = json.loads(row["escalation_reasons"] or "[]")

    answered = _json(row["resolution"], None)

    note, tone = None, None
    if answered:
        note = f"{answered['decision'].capitalize()} by {answered['by']}"
        tone = "info"
    elif state == "needs_you":
        note, tone = "Waiting on your decision", "warn"
    elif state == "failed":
        note = ("No progress recorded for over 15 minutes; the run that owned this is gone."
                if stalled else (row["error"] or "This task stopped without a result."))
        tone = "warn"
    elif state == "queued":
        note, tone = "Delegated, not started", "info"
    elif state == "auditor_review":
        reviewer = AGENTS[agent].reviewer
        note = (f"{AGENTS[reviewer].name} is re-reading the evidence and redoing the maths"
                if reviewer else "Being re-checked independently")
        tone = "info"

    # `failed` is not a board column: the card belongs where a person will look for it,
    # and its note says plainly that nothing was produced.
    column = "needs_you" if state == "failed" else state

    return {
        "id": row["id"],
        "agent": agent,
        "title": row["summary"] or row["objective"] or AGENTS[agent].charter,
        "workflow": row["thread_id"] or "ad hoc",
        "column": column,
        "progress": _progress(row, row["state"]),
        "eta_s": None,
        "started_at": row["started_at"] or row["created_at"],
        "tool_calls": {"used": row["tool_calls"],
                       "budget": row["tool_budget"] or AGENTS[agent].budget.tool_calls},
        "steps": steps,
        "todos": [] if answered else (list(reasons) if state == "needs_you" else []),
        "rationale": row["summary"] or None,
        "note": note,
        "note_tone": tone,
        "approval_id": row["approval_id"],
        # The trail this task wrote, so a card can be tied back to the finding it
        # produced rather than only to the words on its face.
        "decision_id": row["decision_id"],
        # Everything else this task recorded. The drawer shows all of it: what the
        # agent is for, what it was asked, what it spent, what it concluded and what
        # stopped it. A card that shows less than the run recorded is a card that
        # makes a person go and read the database.
        "detail": {
            "agent_name": AGENTS[agent].name,
            "charter": AGENTS[agent].charter,
            "tier": AGENTS[agent].tier,
            "parent": AGENTS[agent].parent,
            "reviewer": AGENTS[agent].reviewer,
            "model": AGENTS[agent].model,
            "objective": row["objective"],
            "summary": row["summary"],
            "state": state,
            "confidence": row["confidence"],
            "cost_cents": row["cost_cents"],
            "model_calls": row["model_calls"],
            "model_budget": row["model_budget"] or AGENTS[agent].budget.model_calls,
            "cost_budget_cents": AGENTS[agent].budget.usd_cents,
            "escalation_reasons": list(reasons),
            "error": row["error"],
            "thread_id": row["thread_id"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "updated_at": row["updated_at"],
            # The output itself, whole. A card in Done that shows only a headline
            # sends a person to the database for the work they just paid for.
            "result": _json(row["result"], {}),
            "review": _json(row["review"], None),
            "resolution": answered,
        },
    }


#: A card still asking a question whose approval has already been decided. Written as
#: one statement because it is a repair, not a feature: `resolve()` keeps new decisions
#: in step, and this catches the ones decided before anything was listening — including
#: every question a person answered while the board went on saying it was outstanding.
CATCH_UP = """
UPDATE agent_tasks SET
    resolution = json_object('decision', (
        SELECT status FROM approvals a
         WHERE a.ws = agent_tasks.ws
           AND (a.id = agent_tasks.approval_id OR a.finding_id = agent_tasks.decision_id)
           AND a.status != 'pending' LIMIT 1), 'by', (
        SELECT COALESCE(decided_by, 'a person') FROM approvals a
         WHERE a.ws = agent_tasks.ws
           AND (a.id = agent_tasks.approval_id OR a.finding_id = agent_tasks.decision_id)
           AND a.status != 'pending' LIMIT 1), 'at', (
        SELECT COALESCE(decided_at, '') FROM approvals a
         WHERE a.ws = agent_tasks.ws
           AND (a.id = agent_tasks.approval_id OR a.finding_id = agent_tasks.decision_id)
           AND a.status != 'pending' LIMIT 1)),
    state = 'done', updated_at = ?
WHERE ws = ? AND resolution IS NULL AND state = 'needs_you' AND EXISTS (
    SELECT 1 FROM approvals a
     WHERE a.ws = agent_tasks.ws
       AND (a.id = agent_tasks.approval_id OR a.finding_id = agent_tasks.decision_id)
       AND a.status != 'pending')
"""


def board(ws: str, limit: int = 120) -> list[dict]:
    """Every task in this workspace, newest first."""
    with db.connect() as connection:
        connection.execute(CATCH_UP, (db.now(), ws))
        rows = connection.execute(
            "SELECT * FROM agent_tasks WHERE ws=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (ws, min(limit, 500))).fetchall()
    now = datetime.now(timezone.utc)
    return [card(row, now) for row in rows]


def live(ws: str) -> dict:
    """The board, plus whether anything is still moving.

    The caller polls, and how often it should poll is a property of the run rather than
    of the screen, so the answer travels with the data.
    """
    tasks = board(ws)
    active = sum(1 for t in tasks if t["column"] in {"queued", "working", "auditor_review"})
    return {
        "tasks": tasks,
        "active": active,
        "waiting": sum(1 for t in tasks if t["column"] == "needs_you"),
        "note": "Every field here is what the run did. Nothing is estimated, and a task "
                "that stopped reporting is shown as stopped rather than as running.",
    }
