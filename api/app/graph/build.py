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

Phase 3 wires the orchestrator and the Treasurer subgraph. B, C and D are registered the
same way, and the orchestrator already knows how to route to them; their subagents' tools
are what remain to be written.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .. import db, ingestion
from ..agents import runtime
from ..agents.budget import BudgetExceeded, Meter, RUN_CAP_CENTS, check_day_cap
from ..agents.registry import AGENTS, children
from ..agents.runtime import AgentFailed
from ..agents.tools import ScopeError
from .state import RunState, initial

#: Worker subgraphs wired so far. The rest are registered as they gain their tools;
#: routing to an unwired worker reports that plainly rather than silently doing nothing.
WIRED_WORKERS = ("A",)


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


def _worker_subgraph(worker_id: str):
    """A worker and its subagents, compiled as one graph.

    The subagents run concurrently: LangGraph fans out on the parallel edges and merges
    what they return through the reducers in `state.py`. They are independent by
    construction — each reads its own scope and none reads another's output — so there is
    no ordering to preserve between them.
    """
    graph = StateGraph(RunState)
    subagents = [spec.id for spec in children(worker_id)]
    for agent_id in subagents:
        graph.add_node(agent_id, _subagent_node(agent_id))
        graph.add_edge(START, agent_id)
        graph.add_edge(agent_id, END)
    return graph.compile()


async def _plan_node(state: RunState) -> dict:
    """Decide which domains this objective touches.

    Deliberately not a model call. Routing between four domains from a sentence is a
    keyword decision, and spending an orchestrator model call on it buys nothing but
    latency and a way to be wrong. The orchestrator's model budget is for synthesis,
    where judgment is actually required.
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
    chosen = [worker for worker, words in domains.items() if any(w in text for w in words)]
    if not chosen:
        # Nothing matched: the treasury view is the one that answers "how are we doing"
        # without assuming a close is in progress.
        chosen = ["A"]

    wired = [w for w in chosen if w in WIRED_WORKERS]
    not_wired = [w for w in chosen if w not in WIRED_WORKERS]
    unresolved = [
        f"{AGENTS[w].name} ({w}) is part of this objective but its subagents are not "
        "wired yet, so nothing was asked of it." for w in not_wired]

    return {
        "plan": wired,
        "plan_rationale": "Routed to " + ", ".join(AGENTS[w].name for w in wired)
                          + " from the objective." if wired else
                          "No wired domain matched this objective.",
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

def build_graph():
    """The whole organization, compiled. Built from the registry, not hand-wired."""
    graph = StateGraph(RunState)
    graph.add_node("plan", _plan_node)
    for worker_id in WIRED_WORKERS:
        graph.add_node(worker_id, _worker_subgraph(worker_id))
        graph.add_edge(worker_id, "synthesize")
    graph.add_node("synthesize", _synthesize_node)

    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", _route,
                                {**{w: w for w in WIRED_WORKERS}, END: END})
    graph.add_edge("synthesize", END)
    return graph.compile()


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
    graph = build_graph()
    # One thread per (workspace, period), so a close that spans days resumes at the node
    # it stopped on rather than starting the period again.
    final = await graph.ainvoke(state, config={
        "configurable": {"thread_id": f"{ws}:{period}:{thread_id}",
                         "meter": meter, "client": client},
        "recursion_limit": 50,
    })
    return {**final, "spend": meter.snapshot(), "thread_id": thread_id}
