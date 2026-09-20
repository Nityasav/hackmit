"""Building and running the graph.

The shape mirrors the organization: an orchestrator node routes, each worker is a
compiled subgraph, and subagents are nodes inside it dispatched with `Send` so a worker
can fan out over however many items its domain turns out to have.

Two decisions worth stating, because both were live options:

**Workers are tools, not handoffs.** A handoff transfers control, and the orchestrator
would lose the thread it needs to combine four domains and to hold one budget across all
of them. Here every delegation returns.

**The budget is one object for the whole run.** It is created once and passed down, so
concurrent branches draw on the same allowance. A per-branch meter would let four agents
each spend the run's cap.

All four workers are wired. The graph is built from the registry, so the topology here
is whatever `registry.py` says it is; adding an agent is a registry edit and a tool, never
a change to this file.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from .. import db, ingestion
from ..agents import activity, runtime
from ..agents.budget import BudgetExceeded, Meter, RUN_CAP_CENTS, check_day_cap
from ..agents.registry import AGENTS, children
from ..agents.runtime import AgentFailed
from ..agents.tools import ScopeError, Toolbox
from . import escalation
from .state import RunState, initial

#: Worker subgraphs wired so far. The rest are registered as they gain their tools;
#: routing to an unwired worker reports that plainly rather than silently doing nothing.
WIRED_WORKERS = ("A", "B", "C", "D")


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #

def _finding(run, event_id: str | None) -> dict:
    result = run.result
    return {
        "agent_id": run.agent_id, "agent_name": AGENTS[run.agent_id].name,
        "event_id": event_id,
        "disposition": result.disposition if result else "insufficient_evidence",
        "summary": result.summary if result else "No result was produced.",
        "rationale": result.rationale if result else "",
        "confidence": run.confidence, "escalated": run.escalated,
        "escalation_reasons": list(run.escalation_reasons),
        "exceptions": [e.model_dump() for e in result.exceptions] if result else [],
        "citations": [c.model_dump() for c in result.citations] if result else [],
        "decision_id": run.decision_id, "cost_cents": run.cost_cents,
    }


def _subagent_node(agent_id: str):
    """One subagent as a graph node. Every subagent is this same function."""

    async def node(state: RunState, config) -> dict:
        spec = AGENTS[agent_id]
        # The meter and the client travel in `configurable`, not in state: they are
        # runtime dependencies rather than data, LangGraph drops state keys the schema
        # does not declare, and a client serialized into a checkpoint would be both
        # meaningless and a leak. One meter for the whole run is what makes concurrent
        # branches draw on a single allowance instead of one each.
        runtime_config = config.get("configurable", {})
        meter: Meter = runtime_config["meter"]
        event_ids = tuple(state.get("event_ids") or ())

        # The graph is compiled once and holds a node for every subagent, but which of
        # them can work depends on what this workspace has committed. The plan decides
        # that; a node nobody assigned returns without spending anything.
        if agent_id not in (state.get("assigned") or []):
            return {}

        try:
            run = await runtime.run_agent(
                state["ws"], agent_id,
                f"{state['objective']}\nYour part: {spec.charter}",
                meter=meter, thread_id=state["thread_id"], event_ids=event_ids,
                client=runtime_config.get("client"))
        except (AgentFailed, BudgetExceeded, ScopeError) as exc:
            # A refusal is a result. Reporting it as an unresolved item keeps the run
            # honest, where swallowing it would make a missing agent look like a clean one.
            return {"unresolved": [f"{spec.name} ({agent_id}): {exc}"],
                    "results": {agent_id: {"error": str(exc), "type": type(exc).__name__}}}

        finding = _finding(run, event_ids[0] if event_ids else None)
        review = await _review(state, run, spec, runtime_config)
        if review:
            finding["review"] = review
        return {
            "findings": [finding],
            "results": {agent_id: run.as_dict()},
            "events_touched": list(event_ids),
            "unresolved": list(run.result.open_questions) if run.result else [],
            "spend_cents": run.cost_cents,
            "model_calls": run.model_calls,
            "tool_calls": run.tool_calls,
            "escalated": run.escalated,
        }

    return node


async def _review(state: RunState, run, spec, runtime_config) -> dict | None:
    """Have the declared independent agent re-check what this one concluded.

    The registry has named a reviewer for most of the organization since it was
    written, and nothing ever called one: `reviewer` was a field the graph did not
    read, so "Auditor review" was a column no card could reach and every finding went
    to a person marked as nobody's work but its own.

    A review is a real task with a real card. It is skipped, and says so, when the
    reviewer cannot read this workspace or the run has no budget left — a review that
    silently did not happen is worse than one that plainly did not.
    """
    reviewer_id = (state.get("reviewers") or {}).get(spec.id)
    if not reviewer_id or run.result is None:
        return None

    activity.mark(run.task_id, "auditor_review")
    reviewer = AGENTS[reviewer_id]
    try:
        verdict_run = await runtime.run_agent(
            state["ws"], reviewer_id,
            f"Re-check {spec.name}'s conclusion, independently.\n"
            f"It concluded: {run.result.summary}\n"
            f"Because: {run.result.rationale}\n"
            "Read the evidence it cited from the originals and reperform every "
            "calculation behind it. Accept only what the records support, and say "
            "plainly which part does not hold if any does not.",
            meter=runtime_config["meter"], thread_id=state["thread_id"],
            event_ids=tuple(state.get("event_ids") or ()),
            client=runtime_config.get("client"))
    except (AgentFailed, BudgetExceeded, ScopeError) as exc:
        activity.mark(run.task_id, "needs_you" if run.escalated else "done")
        return {"reviewer": reviewer_id, "verdict": "not_reviewed", "reason": str(exc)}

    verdict = runtime.VERDICT.get(
        verdict_run.result.disposition if verdict_run.result else "", "needs_evidence")
    runtime.attach_review(state["ws"], run.decision_id, reviewer_id, verdict)
    activity.mark(run.task_id, "needs_you" if run.escalated else "done")
    return {
        "reviewer": reviewer_id, "reviewer_name": reviewer.name, "verdict": verdict,
        "summary": verdict_run.result.summary if verdict_run.result else "",
        "decision_id": verdict_run.decision_id,
    }


def _decision_node(agent_id: str):
    """Stop and wait for a person, if this agent's finding needs one.

    Deliberately its own node. LangGraph re-runs the node that raised an interrupt when
    the run resumes, so anything expensive sitting beside the pause is paid for twice and
    anything non-deterministic beside it changes identity between the question and the
    answer. This node only reads what the working node already wrote.
    """

    async def node(state: RunState) -> dict:
        mine = [f for f in state.get("findings", [])
                if f["agent_id"] == agent_id and f.get("escalated")]
        if not mine:
            return {}
        finding = mine[0]
        outcome = escalation.request_decision(
            ws=state["ws"], agent_id=agent_id, thread_id=state["thread_id"],
            decision_id=finding["decision_id"],
            title=f"{AGENTS[agent_id].name}: {finding['summary'][:120]}",
            summary=finding["rationale"],
            reasons=tuple(finding["escalation_reasons"]),
            event_id=finding.get("event_id"),
            citations=finding.get("citations", []))
        return {"results": {f"{agent_id}:decision": outcome}}

    return node


def _worker_subgraph(worker_id: str):
    """A worker and its subagents, compiled as one graph.

    The subagents run concurrently: LangGraph fans out on the parallel edges and merges
    what they return through the reducers in `state.py`. They are independent by
    construction — each reads its own scope and none reads another's output — so there is
    no ordering to preserve between them.
    """
    graph = StateGraph(RunState)
    for spec in children(worker_id):
        agent_id = spec.id
        decide = f"{agent_id}-decide"
        graph.add_node(agent_id, _subagent_node(agent_id))
        graph.add_node(decide, _decision_node(agent_id))
        graph.add_edge(START, agent_id)
        # Work, then wait. Separating them is what makes a resume free and repeatable.
        graph.add_edge(agent_id, decide)
        graph.add_edge(decide, END)
    return graph.compile()


#: What a worker contributes back to the run, as opposed to what it was handed. Every
#: one of these has a reducer in `state.py`.
CONTRIBUTED = ("findings", "events_touched", "unresolved", "results",
               "spend_cents", "model_calls", "tool_calls", "escalated")


def _worker_node(worker_id: str):
    """A worker subgraph as a node, returning only what it added.

    A compiled subgraph sharing its parent's schema returns the *whole* state it
    finished with, and the parent then applies that as an update. With one worker that
    is harmless. With two it is not: both write `ws`, which has no reducer, and the run
    dies with "can receive only one value per step" — and the additive channels are
    worse than that, because each worker would return the findings it was handed plus
    its own, and the parent would add the handed-in ones a second time.

    The keyword router only ever picked one domain, so nothing exercised it. Routing on
    the records as well means two domains now run together routinely, so the node hands
    back its delta rather than its state.
    """
    subgraph = _worker_subgraph(worker_id)

    async def node(state: RunState, config) -> dict:
        out = await subgraph.ainvoke(state, config)
        delta: dict = {}
        for key in ("findings", "events_touched", "unresolved"):
            before = len(state.get(key) or [])
            added = (out.get(key) or [])[before:]
            if added:
                delta[key] = added
        added_results = {k: v for k, v in (out.get("results") or {}).items()
                         if k not in (state.get("results") or {})}
        if added_results:
            delta["results"] = added_results
        for key in ("spend_cents", "model_calls", "tool_calls"):
            spent = (out.get(key) or 0) - (state.get(key) or 0)
            if spent:
                delta[key] = spent
        if out.get("escalated"):
            delta["escalated"] = True
        return delta

    return node


async def _plan_node(state: RunState) -> dict:
    """Decide who is asked to do what.

    Two inputs, not one. The objective says which domains are *relevant*; the committed
    records say which agents can *work*. Routing on the objective alone is what produced
    a run that delegated four tasks to a Treasurer with no bank statement and no vendor
    bills: every one of them refused in its first few milliseconds, the board filled with
    cards that never moved, and a Controller holding a complete ledger was never asked.

    So an agent is assigned when its domain is in scope and the records its work is
    about are present, and the agents that were passed over say what they are waiting
    for. If the objective names nothing this organization recognizes, every agent that
    can work is put on it — which is what a finance team does with "how are we doing".

    Deliberately not a model call. Choosing among four domains from a sentence is a
    keyword decision; the orchestrator's model budget is for synthesis, where judgment
    is actually required.
    """
    text = state["objective"].lower()
    domains = {
        "A": ("invoice", "payment", "vendor", "bank", "cash", "reconcil", "payable",
              "receivable", "customer", "collect", "payout", "liquidity"),
        "B": ("close", "accrual", "journal", "statement", "balance sheet", "ledger",
              "month-end", "period"),
        "C": ("budget", "forecast", "variance", "plan", "board", "runway"),
        "D": ("audit", "control", "test", "evidence", "compliance", "duplicate",
              "approval", "policy"),
    }
    view = ingestion.coverage(state["ws"])
    stalled: dict[str, list[str]] = view["blocked_agents"]
    labels = {r["id"]: r["label"] for r in view["requirements"]}

    def runnable(worker: str) -> list[str]:
        return [child.id for child in children(worker) if child.id not in stalled]

    matched = [w for w in domains if any(word in text for word in domains[w])]
    wired = [w for w in matched if w in WIRED_WORKERS]
    chosen = [w for w in wired if runnable(w)]

    rationale = ("Routed to " + ", ".join(AGENTS[w].name for w in chosen)
                 + " from the objective." if chosen else "")
    if not chosen:
        chosen = [w for w in WIRED_WORKERS if runnable(w)]
        rationale = (
            "Nothing in the objective named a domain that can work from the committed "
            "records, so it went to every domain that can: "
            + ", ".join(AGENTS[w].name for w in chosen) + "."
            if chosen else
            "No agent can work from the committed records yet.")

    assigned = [agent_id for worker in chosen for agent_id in runnable(worker)]

    # Who was passed over, and for what. An agent missing from the board with no
    # explanation is the same failure as a card that never moves.
    considered = wired or list(WIRED_WORKERS)
    held = {child.id: stalled[child.id]
            for worker in considered for child in children(worker)
            if child.id in stalled}
    unresolved = [
        f"{AGENTS[agent_id].name} ({agent_id}) was not asked: it needs "
        + ", ".join(labels.get(rid, rid) for rid in missing) + ". Supply it on Books."
        for agent_id, missing in sorted(held.items())]
    unresolved += [
        f"{AGENTS[w].name} ({w}) is part of this objective but its subagents are not "
        "wired yet, so nothing was asked of it."
        for w in matched if w not in WIRED_WORKERS]

    # Who re-checks whom. A review is only scheduled where the reviewer can actually
    # read this workspace; a reviewer that would refuse is no review at all.
    reviewers = {agent_id: AGENTS[agent_id].reviewer for agent_id in assigned
                 if AGENTS[agent_id].reviewer and AGENTS[agent_id].reviewer not in stalled}

    # Write the plan down before any of it runs. A delegation only visible once it
    # finishes is indistinguishable from one that never happened, and the board's
    # first column exists to show exactly that gap.
    activity.seed(state["ws"], state["thread_id"], assigned, state["objective"])

    return {
        "plan": chosen,
        "plan_rationale": rationale,
        "assigned": assigned,
        "reviewers": reviewers,
        "unresolved": unresolved,
        "status": "running",
    }


def _route(state: RunState):
    """Dispatch to each planned worker. Returns the node names to run next."""
    return state.get("plan") or [END]


async def _synthesize_node(state: RunState) -> dict:
    """Say what the run found, in figures the agents did not write.

    Every number here is counted from the findings rather than quoted from prose, which
    is the same rule the agents themselves work under.
    """
    findings = state.get("findings", [])
    escalated = [f for f in findings if f.get("escalated")]
    exceptions = [f for f in findings if f.get("disposition") == "exception"]
    unresolved = state.get("unresolved", [])

    if not findings:
        status = "no_findings"
        briefing = ("No agent produced a conclusion for this objective. "
                    + (unresolved[0] if unresolved else "Nothing was asked of any domain."))
    elif escalated:
        status = "needs_you"
        briefing = (f"{len(findings)} conclusion(s), {len(escalated)} needing a person. "
                    f"{len(exceptions)} exception(s) were raised. Nothing has been "
                    "approved, posted or paid.")
    else:
        status = "completed"
        briefing = (f"{len(findings)} conclusion(s), none requiring escalation. "
                    f"{len(unresolved)} open question(s) remain. Reviewer acceptance is "
                    "not human approval.")

    return {"status": status, "briefing": briefing}


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def checkpointer_path() -> str:
    """Where a paused run's state lives.

    Beside the intake database rather than inside it: LangGraph owns this schema and
    migrates it on its own timetable, and mixing the two would make either one's upgrade
    the other's problem.
    """
    root = Path(os.environ.get("SCHOOLTRACE_DATA_DIR",
                               Path(__file__).resolve().parents[2] / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return str(root / "graph-checkpoints.sqlite3")


@asynccontextmanager
async def _saver():
    """The async saver, because the graph is invoked with `ainvoke`.

    The synchronous one raises on every async method, so a run would fail the moment it
    tried to checkpoint — which is exactly the moment an escalation needs it to work.
    """
    async with AsyncSqliteSaver.from_conn_string(checkpointer_path()) as saver:
        yield saver


def build_graph(checkpointer=None):
    """The whole organization, compiled. Built from the registry, not hand-wired."""
    graph = StateGraph(RunState)
    graph.add_node("plan", _plan_node)
    for worker_id in WIRED_WORKERS:
        graph.add_node(worker_id, _worker_node(worker_id))
        graph.add_edge(worker_id, "synthesize")
    graph.add_node("synthesize", _synthesize_node)

    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", _route,
                                {**{w: w for w in WIRED_WORKERS}, END: END})
    graph.add_edge("synthesize", END)
    # Without a checkpointer `interrupt()` cannot resume: the state it paused on would
    # have nowhere to live. Tests that never escalate may compile without one.
    return graph.compile(checkpointer=checkpointer)


async def run_investigation(ws: str, objective: str, *, event_ids: list[str] | None = None,
                            cap_cents: int | None = None, client=None,
                            thread_id: str | None = None) -> dict:
    """Run the organization against one objective, inside one budget."""
    config = ingestion.workspace_config(ws)
    snapshot = ingestion.coverage(ws)["snapshot"]
    if snapshot is None:
        raise AgentFailed("This workspace has no committed snapshot. Commit records first.")

    with db.connect() as connection:
        check_day_cap(connection, ws)

    thread_id = thread_id or db.uid("thread")
    period = str(config.get("start", ""))[:7]
    meter = Meter(run_cap_cents=min(cap_cents or RUN_CAP_CENTS, RUN_CAP_CENTS))

    state = initial(ws, thread_id, objective, snapshot["id"], period, event_ids)
    # One thread per (workspace, period, run), so a close that spans days resumes at the
    # node it stopped on rather than starting the period again.
    config = {"configurable": {"thread_id": f"{ws}:{period}:{thread_id}",
                               "meter": meter, "client": client},
              "recursion_limit": 50}
    async with _saver() as saver:
        final = await build_graph(saver).ainvoke(state, config=config)
    return _outcome(final, meter, thread_id)


def _outcome(final: dict, meter: Meter, thread_id: str) -> dict:
    """One shape whether the run finished or stopped for a person.

    Each pending question carries its own interrupt id, because several agents can stop
    at once and one person's answer must resolve exactly the question they were shown.
    """
    waiting = final.get("__interrupt__") or []
    payloads = [{**getattr(item, "value", item), "interrupt_id": getattr(item, "id", None)}
                for item in waiting]
    return {
        **{k: v for k, v in final.items() if k != "__interrupt__"},
        "spend": meter.snapshot(), "thread_id": thread_id,
        "waiting_on_you": payloads,
        # A paused run is not a finished one, and must never read as though it were.
        "status": "waiting_on_you" if payloads else final.get("status", "completed"),
    }


async def resume_investigation(ws: str, thread_id: str, decision: str, *,
                               approval_id: str | None = None,
                               period: str | None = None, cap_cents: int | None = None,
                               client=None) -> dict:
    """Continue a run that stopped for a person, with what they decided.

    `approval_id` names *which* question is being answered. Several agents can pause in
    one run, and resuming them all with one answer would record a decision on questions
    nobody was shown — so the answer is addressed to a single interrupt by id. Omitting
    it is only safe when exactly one question is outstanding, and this refuses to guess
    when more than one is.

    The meter starts fresh: the earlier spend is already recorded against the decisions
    it paid for, and carrying a spent meter into a resume would refuse work not yet done.
    """
    config_row = ingestion.workspace_config(ws)
    period = period or str(config_row.get("start", ""))[:7]
    meter = Meter(run_cap_cents=min(cap_cents or RUN_CAP_CENTS, RUN_CAP_CENTS))
    config = {"configurable": {"thread_id": f"{ws}:{period}:{thread_id}",
                               "meter": meter, "client": client},
              "recursion_limit": 50}

    async with _saver() as saver:
        graph = build_graph(saver)
        outstanding = await _outstanding(graph, config)
        if not outstanding:
            raise KeyError(f"No paused run with thread {thread_id!r}.")
        target = _addressed(outstanding, approval_id)
        final = await graph.ainvoke(
            Command(resume={target: {"decision": decision}}), config=config)
    return _outcome(final, meter, thread_id)


async def _outstanding(graph, config) -> dict[str, str]:
    """Interrupt id -> the approval it is asking about, for this thread."""
    snapshot = await graph.aget_state(config)
    found = {}
    for task in snapshot.tasks:
        for item in getattr(task, "interrupts", ()) or ():
            value = getattr(item, "value", {}) or {}
            found[getattr(item, "id", "")] = value.get("approval_id", "")
    return found


def _addressed(outstanding: dict[str, str], approval_id: str | None) -> str:
    if approval_id:
        for interrupt_id, proposal in outstanding.items():
            if proposal == approval_id:
                return interrupt_id
        raise KeyError(f"{approval_id!r} is not waiting on this run.")
    if len(outstanding) > 1:
        raise ValueError(
            "This run is waiting on more than one decision. Name the approval you are "
            "answering; resuming them all with one answer would record a decision on "
            "questions nobody was shown.")
    return next(iter(outstanding))
