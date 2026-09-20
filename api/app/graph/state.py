"""What flows through the graph.

One state object per run, checkpointed at every node. The thread is
`(workspace, period)`, so a month-end close can span days and survive a restart: the
graph resumes at the node it stopped on rather than starting the period again.

Reducers matter here. Several agents run concurrently under `Send`, and LangGraph merges
what each returns into one state. A plain assignment would mean the last writer wins and
the others' work vanishes silently — so every field a concurrent node writes to is a list
with an append reducer, and the two scalars that are not (`spend_cents`, `escalated`)
combine by addition and disjunction rather than replacement.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


def _merge_dicts(left: dict, right: dict) -> dict:
    """Later keys win, but neither side is dropped. Used for per-agent maps."""
    return {**left, **right}


def _add_once(left: list, right: list) -> list:
    """Append what is new, and never a conclusion already in the list.

    A checkpointed graph replays. Resuming an interrupt re-runs the node that raised it,
    and invoking a thread again re-applies writes the checkpoint already holds — so a
    plain `operator.add` concatenated the same findings on every resume. Three
    conclusions became the same three twice, then four times, and the counts built on
    them ("3 conclusions recorded") inflated with them.

    A decision id names one recorded decision, so identity is exact and this is a
    deduplication rather than a guess. Order is preserved: the first sighting wins, and
    a later copy is dropped rather than replacing it.
    """
    combined = list(left)
    seen = {item.get("decision_id") for item in combined if item.get("decision_id")}
    for item in right:
        identity = item.get("decision_id")
        if identity and identity in seen:
            continue
        if identity:
            seen.add(identity)
        combined.append(item)
    return combined


def _union(left: list, right: list) -> list:
    """Append, keeping each value once. For plain id lists that replay the same way."""
    combined = list(left)
    for item in right:
        if item not in combined:
            combined.append(item)
    return combined


def _keep_first(left: Any, right: Any) -> Any:
    """For values set once at the start of a run and never legitimately changed.

    Concurrent branches all carry the scope they were given; taking the first keeps
    them from fighting over a value none of them should be rewriting.
    """
    return left if left else right


class Finding(TypedDict, total=False):
    """One thing an agent concluded, flattened for the UI and the report."""

    agent_id: str
    agent_name: str
    event_id: str | None
    disposition: Literal["clear", "exception", "insufficient_evidence"]
    summary: str
    rationale: str
    confidence: int | None
    escalated: bool
    escalation_reasons: list[str]
    exceptions: list[dict]
    citations: list[dict]
    decision_id: str
    cost_cents: int


class RunState(TypedDict, total=False):
    # --- set once, at the start -------------------------------------------
    ws: str
    thread_id: str
    objective: str
    snapshot_id: Annotated[str, _keep_first]
    period: Annotated[str, _keep_first]

    # --- routing ----------------------------------------------------------
    #: Worker ids the orchestrator decided to involve, in order.
    plan: list[str]
    #: Why it chose them. Shown to the person, so it is never omitted.
    plan_rationale: str
    #: Events this run is about, when it is about specific ones.
    event_ids: list[str]

    # --- accumulated by concurrent agents ---------------------------------
    findings: Annotated[list[Finding], _add_once]
    events_touched: Annotated[list[str], _union]
    # Unions too: a replayed branch re-reports the same gap, and the same sentence
    # twice on a screen reads as two problems.
    unresolved: Annotated[list[str], _union]
    #: agent id -> its raw result, for the run detail view.
    results: Annotated[dict[str, dict], _merge_dicts]

    # --- metering ---------------------------------------------------------
    #: Summed across branches rather than overwritten, or concurrent spend is lost.
    spend_cents: Annotated[int, operator.add]
    model_calls: Annotated[int, operator.add]
    tool_calls: Annotated[int, operator.add]

    # --- outcome ----------------------------------------------------------
    #: True when any agent escalated. Disjunction, so one branch cannot clear another.
    escalated: Annotated[bool, operator.or_]
    status: str
    briefing: str


def initial(ws: str, thread_id: str, objective: str, snapshot_id: str,
            period: str, event_ids: list[str] | None = None) -> RunState:
    return RunState(
        ws=ws, thread_id=thread_id, objective=objective, snapshot_id=snapshot_id,
        period=period, plan=[], plan_rationale="", event_ids=event_ids or [],
        findings=[], events_touched=[], unresolved=[], results={},
        spend_cents=0, model_calls=0, tool_calls=0,
        escalated=False, status="queued", briefing="",
    )
