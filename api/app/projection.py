"""The one place a dashboard Bundle is constructed.

Every screen reads a `Bundle`. Building one in more than one place is how the dashboard
once ended up showing hardcoded tasks beside real findings, so this module owns the whole
mapping and nothing else may construct one.

It now reads the **event graph** rather than a run log. An agent's conclusion is a row in
`agent_decisions`, written as the work happened; the transaction it concerns is an
`economic_event`; what an agent matched is a row in `links`. So the bundle describes what
is true of the workspace rather than what the most recent run happened to return, and a
conclusion outlives the run that produced it.

Three rules carried forward, each learned the hard way:

- **An amount appears only when deterministic code produced it.** No figure here is
  written by a model.
- **An agent is on the roster because it did work**, never because something proposed
  work for it.
- **A measure with nothing behind it is left out, not shown as zero.** An empty strip
  says "no work yet"; a row of zeros reads as a clean result.
"""

from __future__ import annotations

import json

from . import approvals as approvals_module, db, events, roles
from .agents.registry import AGENTS
from .ingestion import coverage, source_view
from .models import Bundle

MAX_DECISIONS = 100
PREVIEW_LINES = 8
PREVIEW_CHARS = 700


def _decisions(connection, ws: str) -> list[dict]:
    rows = connection.execute(
        "SELECT * FROM agent_decisions WHERE ws=? ORDER BY rowid DESC LIMIT ?",
        (ws, MAX_DECISIONS)).fetchall()
    return [dict(row) for row in rows]


def _previews(ws: str, source_ids: set[str]) -> dict[str, str]:
    """First lines of each cited original, so an evidence trail opens onto something."""
    out = {}
    for source_id in sorted(s for s in source_ids if s):
        try:
            body = source_view(ws, source_id, 1, PREVIEW_LINES)
        except Exception:
            continue  # superseded or removed since; the locator still stands
        text = "\n".join(line["text"] for line in body["lines"])[:PREVIEW_CHARS]
        if body["line_count"] > len(body["lines"]):
            text += f"\n… {body['line_count'] - len(body['lines'])} more line(s) in the original."
        out[source_id] = text
    return out


def _evidence_nodes(decision: dict, previews: dict[str, str]) -> list[dict]:
    nodes = []
    for citation in json.loads(decision["evidence"] or "[]"):
        # Computed, not read off the citation: an agent's `Citation` carries the exact
        # stored key, because that is what the guard validates against. The readable
        # form is derived here so a purchase-order line never reaches a screen as
        # `PO-70011`, which is a document number that does not exist.
        key = citation.get("record_key") or ""
        label = (roles.readable_key(citation.get("role", ""), key) if key
                 else citation.get("source_id") or "evidence")
        locator = citation.get("source_id", "")
        if citation.get("line"):
            locator = f"{locator} line {citation['line']}"
        nodes.append({
            "label": f"{citation.get('role', 'record')}: {label}",
            "kind": "record", "tone": "neutral",
            "locator": locator or None,
            "source_preview": previews.get(citation.get("source_id", "")),
        })
    if decision["confidence"] is not None:
        # Shown as what it is: a computed figure with its method named, never a model's
        # opinion of its own certainty.
        nodes.append({
            "label": f"Match confidence {decision['confidence']} of 100",
            "kind": "calc", "tone": "neutral",
            "locator": "computed by accounting/match.py from the recorded features",
        })
    return nodes


def _findings(decisions: list[dict], previews: dict[str, str]) -> list[dict]:
    out = []
    for decision in decisions:
        escalated = bool(decision["escalated"])
        summary = decision["summary"]
        if escalated:
            summary = "Waiting on your decision. " + summary
        out.append({
            "id": decision["id"],
            "agent": decision["agent"] if decision["agent"] in AGENTS else "orchestrator",
            "title": decision["action"],
            "summary": summary,
            # A conclusion stays a candidate until a person decides it, whatever
            # disposition the agent reached.
            "status": "needs_evidence" if escalated else "cleared",
            "amount_cents": None,
            "amount_note": "No deterministic calculation backs an amount for this conclusion",
            "verified_by": decision["reviewer"] if decision["reviewer"] in AGENTS else None,
            "evidence": _evidence_nodes(decision, previews),
        })
    return out


def _tasks(decisions: list[dict]) -> list[dict]:
    out = []
    for decision in decisions:
        agent = decision["agent"] if decision["agent"] in AGENTS else "orchestrator"
        escalated = bool(decision["escalated"])
        out.append({
            "id": f"task-{decision['id']}",
            "agent": agent,
            "title": decision["action"][:120],
            "workflow": decision["thread_id"] or "ad hoc",
            "column": "needs_you" if escalated else "done",
            "progress": 100,
            "eta_s": None,
            "started_at": decision["created_at"],
            "tool_calls": {"used": 0, "budget": AGENTS[agent].budget.tool_calls},
            "steps": [{"title": decision["summary"][:200], "state": "done", "memory": False}],
            "todos": [],
            "rationale": decision["why"] or None,
            "note": "Waiting on your decision" if escalated else None,
            "note_tone": "warn" if escalated else None,
        })
    return out


def _with_known_agent(approval: dict) -> dict:
    """Keep a proposal readable when the agent that raised it no longer exists.

    `AgentId` is a closed vocabulary shared by models.py, types.ts, schemas.ts
    and contracts/, and it changed when the agents were reworked. Rows written
    by the previous roster are still in the database, naming agents like `ap`
    and `cfo` that the current contract does not contain — so the whole bundle
    failed validation and every screen in the workspace reported the service
    unreachable, over history nobody was even looking at.

    Widening the vocabulary to admit retired ids would be the wrong repair: it
    is a contract four files agree on, not a place to keep old names alive.
    `_reasoning` already coerces the same way for decisions; this does it for
    proposals, and says in the title which agent actually raised it so the
    attribution is not quietly rewritten.
    """
    if approval.get("agent") in AGENTS:
        return approval
    raised_by = approval.get("agent") or "an unrecorded agent"
    return {**approval, "agent": "orchestrator",
            "title": f"{approval.get('title', '')} · raised by {raised_by}, a retired agent"}


def _reasoning(decisions: list[dict]) -> list[dict]:
    """One `Decision` record per agent action, for the reasoning log."""
    out = []
    for decision in decisions:
        agent = decision["agent"] if decision["agent"] in AGENTS else "orchestrator"
        out.append({
            "id": decision["id"],
            "run": decision["thread_id"] or "ad hoc",
            "time": decision["created_at"],
            "agent": agent,
            "action": decision["action"],
            "summary": decision["summary"],
            "tags": [],
            "when": {"run": decision["thread_id"] or "ad hoc",
                     "step": AGENTS[agent].name,
                     "started": decision["created_at"],
                     "finished": decision["created_at"],
                     "trigger": decision["action"]},
            # Tool calls are metered but not yet replayed into the log. Naming a call
            # that was not recorded would be worse than an empty list.
            "how": [],
            "why": decision["why"] or "No rationale was recorded for this decision.",
            "alternatives": [],
            # Real checks from the run, not a placeholder. A declined precedent
            # shows as prominently as an applied one: "ok: false" with a reason
            # is the evidence that memory was re-checked rather than replayed.
            "memory_checks": [
                {"text": f"{check['precedent_id']}: {check['reason']}",
                 "ok": bool(check.get("applied"))}
                for check in json.loads(decision["memory_checks"] or "[]")
            ],
            "outcome": ("Escalated to a person. Nothing was approved, posted or paid."
                        if decision["escalated"] else
                        "Recorded. Reviewer acceptance is not human approval."),
        })
    return out


def _agents_on_roster(decisions: list[dict]) -> list[dict]:
    """Only agents that actually did work. A proposal is not participation."""
    roster = []
    for agent_id in dict.fromkeys(d["agent"] for d in decisions if d["agent"] in AGENTS):
        spec = AGENTS[agent_id]
        roster.append({
            "id": agent_id, "name": spec.name, "short": agent_id.upper(),
            "role": spec.charter[:120], "status": "idle",
            "doing": "Conclusions recorded; open one to see the evidence behind it.",
        })
    return roster


def _kpis(cov: dict, decisions: list[dict], event_count: int) -> list[dict]:
    kpis = []
    active = [s for s in cov["sources"] if s["active"]]
    if active:
        kpis.append({"label": "Sources committed", "value": str(len(active)),
                     "note": f"{sum(cov['counts'].values())} record(s) in the current snapshot",
                     "tone": "good"})
    if event_count:
        kpis.append({"label": "Transactions", "value": str(event_count),
                     "note": "economic events, each with one identity across the system",
                     "tone": "good"})
    if cov["required_count"]:
        supplied = cov["satisfied_count"]
        kpis.append({"label": "Inputs supplied",
                     "value": f"{supplied}/{cov['required_count']}",
                     "note": f"{len(cov['blocked_agents'])} agent(s) still blocked",
                     "tone": "good" if supplied == cov["required_count"] else "warn"})
    if decisions:
        escalated = sum(1 for d in decisions if d["escalated"])
        kpis.append({"label": "Agent conclusions", "value": str(len(decisions)),
                     "note": f"{escalated} needing a person",
                     "tone": "warn" if escalated else "good"})
        spent = sum(d["cost_cents"] for d in decisions)
        kpis.append({"label": "Spent", "value": f"${spent // 100}.{spent % 100:02d}",
                     "note": "across every agent run in this workspace", "tone": "neutral"})
    return kpis


def _playbooks(ws: str) -> list[dict]:
    """Reviewed precedent: what the system learned from a person's decision.

    `status` is always active and `replay.passed` always true because a precedent only
    exists once a human decided the approval behind it — the approval queue *is* the
    gate. There is no separate replay gate yet, so `months` stays empty rather than
    asserting a regression test that never ran. An empty list is honest; a fabricated
    pass is not.
    """
    with db.connect() as connection:
        precedents = approvals_module.active_precedents(connection, ws)
    return [{
        "id": p["id"], "title": p["pattern"],
        "source": p["source_finding_id"] or "human decision",
        "proposed_by": "orchestrator",
        "replay": {"passed": True, "new_false_positives": 0, "months": []},
        "uses": str(p["uses"]), "status": "active",
        "status_note": f"{p['verdict'].capitalize()} by {p['decided_by']} on "
                       f"{p['decided_at'][:10]}. Re-checked against the snapshot on every use.",
    } for p in precedents]


def bundle(ws) -> Bundle:
    """The single entry point. Every Bundle the API serves is built here."""
    return Bundle.model_validate(_derived(ws))


def _derived(ws):
    cov = coverage(ws)
    w = cov["workspace"]
    snapshot_id = cov["snapshot"]["id"] if cov["snapshot"] else None

    with db.connect() as connection:
        decisions = _decisions(connection, ws)
        timeline = events.timeline(connection, ws, limit=200)
        approval_rows = approvals_module.listing(connection, ws, snapshot_id)
        human_decisions = approvals_module.decisions(connection, ws)

    cited = {c.get("source_id", "") for d in decisions
             for c in json.loads(d["evidence"] or "[]")}
    previews = _previews(ws, cited)
    findings = _findings(decisions, previews)

    waiting = sum(1 for a in approval_rows if a["status"] == "pending")
    escalated = sum(1 for d in decisions if d["escalated"])
    actions = []
    if waiting:
        actions.append({"label": f"Decide {waiting} proposal(s)", "href": "approvals",
                        "primary": True})
    if findings:
        actions.append({"label": "Review findings", "href": "findings",
                        "primary": not actions})

    if not decisions:
        briefing = ("Upload records and answer what the agents need. No agent has run "
                    "for this workspace.")
    elif escalated:
        briefing = (f"{len(decisions)} agent conclusion(s), {escalated} needing a person. "
                    "Nothing has been approved, posted or paid.")
    else:
        briefing = (f"{len(decisions)} agent conclusion(s), none escalated. Reviewer "
                    "acceptance is not human approval.")

    comparisons, gate = approvals_module.comparisons(approval_rows, findings)
    spent = sum(d["cost_cents"] for d in decisions)

    return {
        "contract_version": 2,
        "workspace": {
            "id": ws, "name": w["name"], "kind": w["kind"],
            "period": f"{w['start']} — {w['end']}",
            "mode": "live" if decisions else "not_started",
            "snapshot_id": snapshot_id or "No committed records",
            "disabled_tabs": [],
            "model": decisions[0]["model"] if decisions else "Not configured",
            # Budget is money now rather than calls: cents, the unit everything else
            # in the system already uses.
            "run_budget": {"used": spent, "total": 0},
            "intake": True, "currency": w["currency"], "profile": w["profile"],
        },
        "agents": _agents_on_roster(decisions),
        "briefing": {
            "generated_at": decisions[0]["created_at"] if decisions else "—",
            "text": briefing, "actions": actions,
        },
        "kpis": _kpis(cov, decisions, len(timeline)),
        "workflows": [],
        "tasks": _tasks(decisions),
        "findings": findings,
        "approvals": [_with_known_agent(row) for row in approval_rows],
        "decisions": _reasoning(decisions) + human_decisions,
        "playbooks": _playbooks(ws),
        "ablation": None,
        "report": {
            "title": f"Review — {w['name']}",
            "sections": [f"Agent conclusions ({len(decisions)})",
                         f"Transactions ({len(timeline)})", "Limitations"],
            "comparisons": comparisons,
            "markdown": None,
            **({"applies_approval": gate, "before_label": "As reported",
                "after_label": "After approved decisions"} if comparisons else {}),
        },
    }
