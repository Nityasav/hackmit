"""CFO Agent tools: assign_task and write_briefing.

Unlike ap_tools/ap_write_tools, these are not plain functions in a static
registry. assign_task is the actual handoff point this phase is about: it
creates a Task (so the work is visible on the Agent board, not a detached
function call), hands its exact question to the named specialist's own agent
loop (run_ap_agent / run_auditor_agent), and that loop updates the Task live
as it works. That needs a workspace, a specialist tool budget, and an OpenAI
client — run-scoped context a plain function signature can't carry, so
run_loop binds these as closures per CFO run, the same pattern as
record_decision (see decision_tools.py).

assign_task runs the specialist synchronously and returns its result. There is
no queue or background worker here — this is still one process reasoning
step by step, just now with a real caller/callee relationship between agents
instead of every run starting from a bare, unassigned question.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from .. import store

AGENT_ID = "cfo"

ASSIGN_TASK_SPEC: dict[str, Any] = {
    "type": "function",
    "name": "assign_task",
    "description": "Create a bounded task and hand it to a specialist right now. Runs the specialist's "
    "full investigation synchronously and returns its final answer, its decision id, and where "
    "the task landed on the Agent board (done / needs_you / auditor_review). Give the specialist "
    "a specific question with a clear scope — it cannot ask you a follow-up mid-run, so an vague "
    "question wastes its tool budget.",
    "parameters": {
        "type": "object",
        "properties": {
            "agent": {
                "type": "string",
                "enum": ["ap", "au"],
                "description": "'ap' for AP & Payments (invoices, vendors, POs, receipts, payment batches). "
                "'au' for Internal Auditor (independently re-check one specific finding by ID).",
            },
            "title": {"type": "string", "description": "Short task title for the Agent board."},
            "workflow": {"type": "string", "description": "Workflow this task belongs to, e.g. 'AP & payments'."},
            "question": {
                "type": "string",
                "description": "The specialist's exact scope: what to investigate, or which finding id to review.",
            },
        },
        "required": ["agent", "title", "workflow", "question"],
    },
}

WRITE_BRIEFING_SPEC: dict[str, Any] = {
    "type": "function",
    "name": "write_briefing",
    "description": "Write the Command center briefing. Use only accepted findings, open tasks, and "
    "pending approvals — never an unreviewed specialist claim. Overwrites the current briefing.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Briefing text. **bold** marks highlights."},
            "actions": {
                "type": "array",
                "description": "Buttons for the human, e.g. [{'label': 'Review approvals', 'href': 'approvals'}].",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "href": {"type": "string"},
                        "primary": {"type": "boolean"},
                    },
                    "required": ["label", "href"],
                },
            },
        },
        "required": ["text"],
    },
}


def bind_assign_task(*, workspace: str, client: Any, specialist_budget: int) -> Callable[..., dict[str, Any]]:
    from .run_loop import run_ap_agent, run_auditor_agent  # local import: run_loop imports cfo_tools

    runners: dict[str, Callable[..., Any]] = {"ap": run_ap_agent, "au": run_auditor_agent}

    def assign_task(
        agent: str,
        title: str,
        workflow: str,
        question: str,
        **_ignored: Any,
    ) -> dict[str, Any]:
        if agent not in runners:
            raise ValueError(f"no such specialist '{agent}' — only 'ap' or 'au'")

        task_id = store.next_id(workspace, "tasks", "T-", width=3)
        store.create_task(
            workspace,
            {
                "id": task_id,
                "agent": agent,
                "title": title,
                "workflow": workflow,
                "column": "working",
                "progress": 0,
                "eta_s": None,
                "started_at": time.strftime("%H:%M:%S"),
                "tool_calls": {"used": 0, "budget": specialist_budget},
                "steps": [],
                "todos": [],
                "rationale": None,
            },
        )

        result = runners[agent](
            question,
            workspace=workspace,
            budget=specialist_budget,
            client=client,
            task_id=task_id,
        )

        task = next(t for t in store.get_bundle(workspace).tasks if t.id == task_id)
        return {
            "task_id": task_id,
            "column": task.column,
            "specialist_answer": result.answer,
            "decision_id": result.decision_id,
            "tool_calls_used": result.tool_calls_used,
        }

    return assign_task


def bind_write_briefing(*, workspace: str) -> Callable[..., dict[str, Any]]:
    def write_briefing(
        text: str,
        actions: list[dict[str, Any]] | None = None,
        **_ignored: Any,
    ) -> dict[str, Any]:
        record = store.set_briefing(
            workspace,
            {"generated_at": time.strftime("%H:%M"), "text": text, "actions": actions or []},
        )
        return {"filed": True, "generated_at": record.generated_at}

    return write_briefing
