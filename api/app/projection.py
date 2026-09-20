"""The one place a dashboard Bundle is constructed.

Every tab reads a `Bundle`. Building one in more than one place is how the
dashboard ended up showing hardcoded tasks next to real findings, so this module
owns the whole mapping and no other module may construct a `Bundle`.

Two kinds of run feed it, and both now live in the same database (`app/db.py`):

- snapshot triage runs (`agent_runs`, written by `app/agents/cfo.py`) - the CFO,
  Grants and Internal Auditor agents working a committed snapshot on their own;
- coordinator runs (`cfo_runs`, written by `app/cfo/engine.py`) - the five-agent
  workflow, whose accepted claims have already survived independent review.

A claim only carries an amount when a deterministic calculation produced it. The
model never supplies a number that reaches this layer.
"""

from __future__ import annotations

from collections import Counter
import json

from fastapi import HTTPException

from . import approvals as approvals_module, db, store
from .ingestion import coverage, financial_records, source_view
from .models import Bundle

AGENTS = {
    "cfo": {"id": "cfo", "name": "CFO Agent", "short": "CFO", "role": "Lead investigator / orchestrator"},
    "ap": {"id": "ap", "name": "AP & Payments", "short": "AP", "role": "Invoices, POs, receipts and payment support"},
    "py": {"id": "py", "name": "Payroll & Budget", "short": "PY", "role": "Payroll tie-out and fund allocation"},
    "gr": {"id": "gr", "name": "Grants & Compliance", "short": "GR", "role": "Restricted-funds specialist"},
    "au": {"id": "au", "name": "Internal Auditor", "short": "AU", "role": "Independent reviewer"},
}

#: Triage run `agent` column -> roster key.
TRIAGE_AGENTS = {"cfo": "cfo", "grants_compliance": "gr", "internal_auditor": "au"}

#: Coordinator task status -> the board column the contract defines.
TASK_COLUMN = {
    "queued": "queued", "working": "working", "auditor_review": "auditor_review", "done": "done",
    "needs_evidence": "needs_you", "failed": "needs_you", "blocked": "needs_you",
}

#: Claim disposition -> finding status. Both vocabularies are deliberately the same.
DISPOSITION = {"substantiated": "substantiated", "cleared": "cleared", "explained": "explained"}

MAX_RUNS = 20
PREVIEW_LINES = 8
PREVIEW_CHARS = 700

#: Workspaces served from a recorded fixture rather than derived from runs.
#: Phase 8 regenerates these by running the real pipeline, which closes this seam.
RECORDED = {"sandbox", "mit"}


# --------------------------------------------------------------------------- #
# Snapshot triage runs
# --------------------------------------------------------------------------- #

def _triage_projection(run):
    agent = AGENTS[TRIAGE_AGENTS[run["agent"]]]
    output = json.loads(run["output"]) if run else {}
    analysis = output.get("analysis", {})
    role_ids = {"ap_payments": "ap", "payroll_budget": "py", "grants_compliance": "gr", "internal_auditor": "au"}
    tasks = [{
        "id": f"{run['id']}-task-{index}", "agent": role_ids[task["specialist"]], "title": task["title"],
        "workflow": agent["name"] + " follow-up", "column": "queued", "progress": 0, "eta_s": None,
        "started_at": None, "tool_calls": {"used": 0, "budget": 12},
        "steps": [{"title": task["objective"], "state": "todo", "memory": False}], "todos": [],
        "rationale": "Proposed by " + agent["name"] + "; this follow-up has not been executed.",
        "note": "Candidate task", "note_tone": "info",
    } for index, task in enumerate(analysis.get("next_tasks", []), 1)]
    findings = [{
        "id": f"{run['id']}-finding-{index}", "agent": agent["id"], "title": finding["title"],
        "summary": agent["name"] + " candidate · independent review pending. " + finding["summary"],
        "status": "hypothesized" if finding["status"] == "cleared" else finding["status"],
        "amount_cents": None, "amount_note": "No independently reviewed finding amount", "verified_by": None,
        "evidence": [{"label": f"{cite['source_id']} line {cite['line']}: {cite['quote']}",
                      "kind": "doc", "tone": "neutral",
                      "locator": f"{cite['source_id']} line {cite['line']}"} for cite in finding["citations"]],
    } for index, finding in enumerate(analysis.get("findings", []), 1)]
    decision = output.get("decision", {})
    decisions = [{
        "id": f"decision-{run['id']}", "run": run["id"], "time": run["completed_at"], "agent": agent["id"],
        "action": decision.get("action", "Initial snapshot triage"),
        "summary": decision.get("summary", analysis.get("executive_briefing", "")), "tags": [],
        "when": {"run": run["id"], "step": agent["name"] + " review", "started": run["created_at"],
                 "finished": run["completed_at"], "trigger": run["focus"]},
        "how": [{"tool": item["tool"], "input": item["input_hash"], "output": item["output_ref"]}
                for item in output.get("tool_calls", [])],
        "why": decision.get("why", "Identify bounded follow-up work from committed evidence."),
        "alternatives": [], "memory_checks": [],
        "outcome": decision.get("outcome", "Candidate triage saved."),
    }]
    return tasks, findings, decisions


# --------------------------------------------------------------------------- #
# Coordinator runs
# --------------------------------------------------------------------------- #

def _evidence_nodes(accepted, sources, previews):
    """Cited sources, plus the calculation when one backs the amount."""
    nodes = []
    for source_id in dict.fromkeys(accepted["claim"]["evidence_ids"]):
        source = sources.get(source_id)
        nodes.append({
            "label": source["title"] if source else source_id,
            "kind": "doc", "tone": "neutral",
            # The coordinator cites whole sources, so there is no line to point at.
            # Saying so beats inventing a line number the reader could not verify.
            "locator": source["locator"] if source else source_id,
            "source_preview": previews.get(source_id),
        })
    calculation = accepted.get("calculation")
    if calculation:
        nodes.append({
            "label": calculation["description"], "kind": "calc", "tone": "neutral",
            "locator": f"{calculation['id']} · reperformed by the Internal Auditor",
        })
    return nodes


def _coordinator_findings(run, previews):
    sources = {s["id"]: s for s in (run.get("scope") or {}).get("sources", [])}
    findings = []
    for accepted in run["accepted"]:
        claim, review = accepted["claim"], accepted["review"]
        calculation = accepted.get("calculation")
        findings.append({
            "id": f"{run['id']}-{claim['id']}", "agent": accepted["role"], "title": claim["title"],
            "summary": f"{claim['conclusion']} Internal Auditor accepted this claim: {review['rationale']} "
                       "Human approval remains separate.",
            "status": DISPOSITION[claim["disposition"]],
            # An amount exists only when the engine produced one and the auditor reperformed it.
            "amount_cents": calculation["amount_cents"] if calculation else None,
            "amount_note": (f"{calculation['category'].replace('_', ' ')}; cash impact "
                            f"{calculation['cash_delta_cents']} cents")
                           if calculation else "No deterministic calculation backs an amount for this claim",
            "verified_by": "au",
            "evidence": _evidence_nodes(accepted, sources, previews),
        })
    return findings


def _previews(ws, source_ids):
    """First lines of each cited original, so the evidence trail opens onto something.

    Read once per bundle and shared across every node that cites the source, and
    only for sources a claim actually names.
    """
    previews = {}
    for source_id in sorted(source_ids):
        try:
            body = source_view(ws, source_id, 1, PREVIEW_LINES)
        except HTTPException:
            continue  # superseded or removed since the run; the locator still stands
        text = "\n".join(line["text"] for line in body["lines"])[:PREVIEW_CHARS]
        if body["line_count"] > len(body["lines"]):
            text += f"\n… {body['line_count'] - len(body['lines'])} more line(s) in the original."
        previews[source_id] = text
    return previews


def _coordinator_tasks(run):
    plan_rationale = (run.get("plan") or {}).get("rationale")
    budget = run["request"]["limits"]["tool_calls_per_agent_task"]
    accepted_by_task = {}
    for accepted in run["accepted"]:
        accepted_by_task.setdefault(accepted["task_id"], []).append(accepted["claim"]["title"])
    tasks = []
    for state in run["tasks"]:
        spec, status = state["spec"], state["status"]
        result = state.get("result") or {}
        claims = accepted_by_task.get(spec["id"], [])
        step_state = "done" if status == "done" else "running" if status in {"working", "auditor_review"} else "todo"
        steps = [{"title": spec["objective"], "state": step_state, "memory": False}]
        if result.get("summary"):
            steps.append({"title": "Specialist result", "detail": result["summary"],
                          "state": "done", "memory": False})
        if claims:
            steps.append({"title": f"{len(claims)} claim(s) accepted by the Internal Auditor",
                          "detail": "; ".join(claims), "state": "done", "memory": False})
        tasks.append({
            "id": f"{run['id']}-{spec['id']}", "agent": spec["role"], "title": spec["objective"][:120],
            "workflow": run["id"], "column": TASK_COLUMN[status],
            "progress": 100 if status == "done" else 60 if status == "auditor_review"
                        else 30 if status == "working" else 0,
            "eta_s": None, "started_at": run["created_at"],
            "tool_calls": {"used": state["tool_calls"], "budget": budget},
            "steps": steps,
            "todos": list(result.get("evidence_requests", [])),
            "rationale": plan_rationale,
            "note": {"needs_evidence": "Missing evidence", "failed": "Stopped without accepting claims",
                     "blocked": "Upstream work unresolved"}.get(status),
            "note_tone": "warn" if status in {"needs_evidence", "failed", "blocked"} else None,
        })
    return tasks


#: Coordinator task status -> the stage state the Workflows tab draws.
STAGE_STATE = {
    "done": "done", "working": "running", "auditor_review": "running",
    "needs_evidence": "human", "failed": "human", "blocked": "human", "queued": "todo",
}


def _coordinator_workflow(run):
    """One workflow per run: the DAG the coordinator actually executed.

    Stages are not authored anywhere. They are the plan's tasks, in the order the
    engine ran them, wrapped by the two steps every run has: planning it, and
    publishing what survived review.
    """
    stages = [{"name": "Plan", "state": "done" if run.get("plan") else "todo"}]
    for state in run["tasks"]:
        stages.append({"name": AGENTS[state["spec"]["role"]]["short"] + " " + state["spec"]["id"],
                       "state": STAGE_STATE[state["status"]]})
    published = bool(run["report_markdown"])
    stages.append({"name": "Report", "state": "done" if published else
                   "human" if run["status"] in {"needs_evidence", "partial"} else "todo"})
    done = sum(1 for stage in stages if stage["state"] == "done")
    return {
        "id": run["id"],
        "name": run["request"]["objective"][:90],
        # The CFO owns the run; the specialists own the stages inside it.
        "owner": "cfo",
        "progress": round(done * 100 / len(stages)),
        "stages": stages,
    }


def _tool_calls_for(events, task_id):
    """Evidence reads and calculations an actor actually performed, for the `how` trail."""
    return [{"tool": event["action"].removesuffix(".completed"),
             "input": ", ".join(event["references"]) or task_id or "—",
             "output": event["detail"][:300]}
            for event in events
            if event["task_id"] == task_id
            and event["action"] in {"read_source.completed", "calculate.completed"}]


def _coordinator_decisions(run):
    """One decision record per decision, not per event.

    The full event stream stays on the run detail page; the Reasoning log gets the
    points where an agent actually chose something.
    """
    events = run["events"]
    decisions = []

    def add(event, agent, action, summary, why, outcome, how=None):
        decisions.append({
            "id": f"decision-{run['id']}-{len(decisions) + 1}", "run": run["id"], "time": event["at"],
            "agent": agent, "action": action, "summary": summary, "tags": [],
            "when": {"run": run["id"], "step": event["action"], "started": run["created_at"],
                     "finished": event["at"], "trigger": run["request"]["objective"]},
            "how": how or [], "why": why, "alternatives": [],
            "memory_checks": [], "outcome": outcome,
        })

    specs = {state["spec"]["id"]: state["spec"] for state in run["tasks"]}
    for event in events:
        action = event["action"]
        if action == "plan.accepted":
            add(event, "cfo", "Plan the investigation",
                f"{len(run['tasks'])} task(s) delegated across the specialist agents.",
                event["detail"], "Plan accepted; specialists dispatched.")
        elif action.startswith("review."):
            verdict = action[len("review."):]
            if verdict in {"accept", "reject", "needs_evidence"}:
                claim_id = event["references"][0] if event["references"] else "claim"
                add(event, "au", f"Review {claim_id}: {verdict}", event["detail"],
                    "Independent reperformance against freshly retrieved originals.",
                    f"Verdict {verdict}.", how=_tool_calls_for(events, event["task_id"]))
        elif action in {"task.finished", "task.failed", "task.blocked"}:
            spec = specs.get(event["task_id"])
            if spec:
                # A task that failed or was blocked is a decision the log must carry;
                # dropping it would make an abandoned task look like it never ran.
                verb = {"task.finished": "Finish", "task.failed": "Abandon",
                        "task.blocked": "Block"}[action]
                add(event, spec["role"], f"{verb} {event['task_id']}",
                    f"Task ended in state: {event['detail']}.", spec["success_criteria"],
                    event["detail"], how=_tool_calls_for(events, event["task_id"]))
        elif action in {"report.published", "run.failed", "run.interrupted"}:
            add(event, "cfo", "Publish the run outcome", event["detail"],
                "Only independently reviewed claims may enter the report.",
                f"Run status: {run['status']}.")
    return decisions


def _money(cents):
    sign = "-" if cents < 0 else ""
    units, remainder = divmod(abs(cents), 100)
    return f"{sign}${units:,}.{remainder:02d}"


def _kpis(cov, findings, triage, coordinator):
    """Five numbers, each traceable to a query.

    A measure with nothing behind it is left out rather than shown as zero: an
    empty strip says "no work yet", where a row of zeros reads as a clean result.
    """
    kpis = []

    active = [s for s in cov["sources"] if s["active"]]
    if active:
        records = sum(cov["counts"].values())
        kpis.append({"label": "Sources committed", "value": str(len(active)),
                     "note": f"{records} record(s) in the current snapshot", "tone": "good"})

    requests = cov["requests"]
    if requests:
        open_requests = [r for r in requests if r["status"] in {"open", "needs_review"}]
        kpis.append({"label": "Evidence gaps", "value": str(len(open_requests)),
                     "note": f"of {len(requests)} request(s) raised",
                     "tone": "warn" if open_requests else "good"})

    if findings:
        reviewed = sum(1 for f in findings if f["verified_by"])
        kpis.append({"label": "Findings", "value": str(len(findings)),
                     "note": f"{reviewed} independently reviewed",
                     "tone": "good" if reviewed == len(findings) else "warn"})

        # Only amounts the engine produced and the auditor reperformed are summed.
        priced = [f["amount_cents"] for f in findings if f["amount_cents"] is not None]
        if priced:
            kpis.append({"label": "Reviewed exposure", "value": _money(sum(priced)),
                         "note": f"across {len(priced)} of {len(findings)} finding(s) with a calculation",
                         "tone": "warn"})

    if triage or coordinator:
        used = sum(len(json.loads(r["output"]).get("tool_calls", [])) for r in triage)
        used += sum(run["tool_calls"] for run in coordinator)
        models = sum(run["model_calls"] for run in coordinator)
        kpis.append({"label": "Evidence calls", "value": str(used),
                     "note": f"{len(triage) + len(coordinator)} run(s); {models} coordinator model call(s)",
                     "tone": "good"})
    return kpis


def _report(cov, findings, coordinator, comparisons, gate):
    """The run's own published report, not a second rendering of it.

    `app/cfo/reporting.py` already composes this from accepted claims, with the
    money injected by the renderer rather than written by the model, so the
    export is that document verbatim.
    """
    published = next((run for run in coordinator if run["report_markdown"]), None)
    if not published:
        return {"title": "No investigation report yet", "sections": [], "comparisons": [], "markdown": None}

    labels = {"before_label": "As reported", "after_label": "After approved decisions",
              "applies_approval": gate} if comparisons else {}

    scope = published.get("scope") or {}
    reviewed = len(published["accepted"])
    unresolved = len(published["unresolved"])
    return {
        "title": f"CFO review — {scope.get('institution', cov['workspace']['name'])}",
        "sections": [
            f"Reviewed conclusions ({reviewed})",
            f"Unresolved matters ({unresolved})",
            "Limitations",
        ],
        # An "after" exists only because a decision exists.
        "comparisons": comparisons,
        "markdown": published["report_markdown"],
        **labels,
    }


#: Which of a task's approvals `Task.approval_id` names when it has several. The
#: contract carries one id, so it names the one that still needs a person:
#: pending first, then a rejection whose work may have to be redone, and last an
#: approval that is already settled.
APPROVAL_URGENCY = {"pending": 0, "rejected": 1, "approved": 2}


def _approval_note(linked):
    """How a task's proposals stand, in one line.

    A task with a single proposal reads exactly as it always did. A task with
    several is counted instead, because one status cannot describe two different
    outcomes, and an approved proposal beside a rejected one is not "approved".
    """
    if len(linked) == 1:
        approval_id, status = linked[0]
        return f"{approval_id} {status}"
    counts = Counter(status for _, status in linked)
    return ", ".join(f"{counts[s]} {s}" for s in ("pending", "approved", "rejected") if counts[s])


def _link_approvals(tasks, task_approvals):
    """Point every task at all of its proposals, not just the last one written."""
    for task in tasks:
        linked = task_approvals.get(task["id"])
        if not linked:
            continue
        task["approval_id"] = min(linked, key=lambda item: APPROVAL_URGENCY[item[1]])[0]
        decided = [item for item in linked if item[1] != "pending"]
        if len(decided) < len(linked):
            task["column"], task["note_tone"] = "needs_you", "warn"
            # Anything already settled is named too, so a part-decided task does
            # not read as though nothing has happened on it yet.
            task["note"] = ("Waiting on your decision" if not decided
                            else f"Waiting on your decision · {_approval_note(linked)}")
        else:
            # Every proposal is decided, so the task's own derived state is the
            # honest column again. The note carries what was decided, and a
            # rejection is an outcome the board must be able to show.
            task["note"] = _approval_note(linked)
            task["note_tone"] = "warn" if any(s == "rejected" for _, s in linked) else "info"


def _note_decisions_on_findings(findings, approvals):
    """Say on a finding that its proposal was decided, and how.

    `Finding.status` is a closed vocabulary in the contract and none of its values
    means "a human decided this", so the decision rides in the summary the same
    way the auditor's verdict already does. Without it the Findings tab is
    byte-identical before and after a decision.
    """
    decided = {}
    for approval in approvals:
        if approval["finding_id"] and approval["status"] != "pending":
            decided.setdefault(approval["finding_id"], []).append(
                (approval["id"], approval["status"]))
    for finding in findings:
        outcomes = decided.get(finding["id"])
        if outcomes:
            finding["summary"] = ("Your decision: "
                                  + "; ".join(f"{i} {s}" for i, s in outcomes)
                                  + ". ") + finding["summary"]


def _disabled_tabs(workspace):
    """Which tabs this workspace has no business showing.

    Learning belongs to another workstream. Approvals and Workflows depend on the
    workspace: a public-documents workspace holds published reports and no
    transactions, so there is nothing to decide and no close to run.
    """
    disabled = ["learning"]
    if workspace["kind"] == "public":
        disabled = ["workflows", "approvals", "learning"]
    return disabled


def _load_runs(connection, ws, snapshot_id):
    """Coordinator runs planned against the snapshot now in force.

    A run whose scope names an older snapshot describes evidence that has since
    been superseded, so it is left out rather than shown as current.
    """
    if not snapshot_id:
        return []
    rows = connection.execute(
        "SELECT payload FROM cfo_runs WHERE workspace=? ORDER BY created_at DESC LIMIT ?",
        (ws, MAX_RUNS),
    ).fetchall()
    runs = []
    for row in rows:
        run = json.loads(row["payload"])
        scope = run.get("scope") or {}
        if scope.get("snapshot_id") == snapshot_id and run["status"] != "stale":
            runs.append(run)
    return runs


# --------------------------------------------------------------------------- #
# The bundle
# --------------------------------------------------------------------------- #

def bundle(ws) -> Bundle:
    """The single entry point. Every Bundle the API serves is built here."""
    if ws in RECORDED:
        return store.get_bundle(ws)
    return Bundle.model_validate(_derived(ws))


def _derived(ws):
    cov = coverage(ws)
    w = cov["workspace"]
    snapshot_id = cov["snapshot"]["id"] if cov["snapshot"] else None
    with db.connect() as connection:
        # Recover abandoned runs even if only the dashboard bundle is being polled.
        from .agents.cfo import _expire_runs
        _expire_runs(connection, ws)
        running = connection.execute(
            "SELECT * FROM agent_runs WHERE ws=? AND status='running' ORDER BY created_at DESC LIMIT 1", (ws,),
        ).fetchone()
        triage = [row for agent in TRIAGE_AGENTS if (row := connection.execute(
            "SELECT * FROM agent_runs WHERE ws=? AND snapshot_id=? AND agent=? AND status='completed' ORDER BY created_at DESC LIMIT 1",
            (ws, snapshot_id, agent),
        ).fetchone())] if snapshot_id else []
        audit_history = connection.execute(
            "SELECT output FROM agent_runs WHERE ws=? AND snapshot_id=? AND agent='internal_auditor' AND status='completed' ORDER BY created_at DESC LIMIT 20",
            (ws, snapshot_id),
        ).fetchall() if snapshot_id else []
        # Same transaction, same snapshot: the whole point of moving cfo_runs here.
        coordinator = _load_runs(connection, ws, snapshot_id)

    tasks, findings, decisions = [], [], []
    triage_findings = {}
    for saved in triage:
        t, f, d = _triage_projection(saved)
        triage_findings[saved["id"]] = f
        tasks.extend(t); findings.extend(f); decisions.extend(d)

    # Verdicts are attached only to their exact preparer-run finding IDs. Rerunning a
    # preparer cannot silently inherit an old review, even on the same source snapshot.
    latest_reviews = {}
    for saved in audit_history:
        for review in json.loads(saved["output"]).get("analysis", {}).get("reviews", []):
            latest_reviews.setdefault(review["finding_id"], review)
    for finding in findings:
        review = latest_reviews.get(finding["id"])
        if review:
            finding["summary"] = (f"Internal Auditor: {review['verdict']} — {review['rationale']} "
                                  "Human approval remains separate. ") + finding["summary"].replace(
                "candidate · independent review pending.", "candidate · bounded review recorded.")

    # A completed run's proposals are written once, then owned by the approvals
    # table: a rerun cannot silently un-decide something a human already decided.
    # Triage candidates propose too, but only whether to pursue them: they carry no
    # independent review and no calculation, so they can never move money.
    for saved in triage:
        approvals_module.sync_triage(ws, saved["id"], snapshot_id, triage_findings[saved["id"]])
    if coordinator:
        records = financial_records(ws)["records"]
        for run in coordinator:
            if run["status"] not in {"queued", "planning", "running"}:
                approvals_module.sync(ws, run, records)
    with db.connect() as connection:
        approval_rows = approvals_module.listing(connection, ws, snapshot_id)
        human_decisions = approvals_module.decisions(connection, ws)
        # A task may raise several proposals, so every one is kept. Keying by task
        # alone let the second approval overwrite the first, which hid whichever
        # outcome happened to be written last.
        task_approvals = {}
        for row in connection.execute(
                "SELECT id, run_id, task_id, status FROM approvals"
                " WHERE ws=? AND task_id IS NOT NULL ORDER BY rowid", (ws,)):
            task_approvals.setdefault(f"{row['run_id']}-{row['task_id']}", []).append(
                (row["id"], row["status"]))

    cited = {source_id for run in coordinator for accepted in run["accepted"]
             for source_id in accepted["claim"]["evidence_ids"]}
    previews = _previews(ws, cited)
    for run in coordinator:
        findings.extend(_coordinator_findings(run, previews))
        tasks.extend(_coordinator_tasks(run))
        decisions.extend(_coordinator_decisions(run))

    # The briefing comes from whichever run most recently published one.
    triage_run = triage[0] if triage else None
    triage_analysis = json.loads(triage_run["output"]).get("analysis", {}) if triage_run else {}
    reported = next((r for r in coordinator if r["status"] != "queued"), None)
    briefing_text = triage_analysis.get("executive_briefing") or (reported["briefing"] if reported else None)
    generated_at = (triage_run["completed_at"] if triage_run else None) or (
        reported["updated_at"] if reported else "—")

    # An agent is on the roster because it did work, not because someone proposed
    # work for it. A CFO run that suggests a Grants follow-up does not make Grants
    # an agent that has run.
    worked = {TRIAGE_AGENTS[run["agent"]] for run in triage}
    for run in coordinator:
        worked |= {state["spec"]["role"] for state in run["tasks"]}
        if run.get("plan"):
            worked.add("cfo")
        if any(event["action"].startswith("review.") for event in run["events"]):
            worked.add("au")
    agents = []
    for key, meta in AGENTS.items():
        triage_name = next((n for n, r in TRIAGE_AGENTS.items() if r == key), None)
        live = running is not None and triage_name is not None and running["agent"] == triage_name
        if not live and key not in worked:
            continue
        agents.append({**meta, "status": "working" if live else "idle",
                       "doing": "Reviewing snapshot evidence" if live else
                                "Bounded review saved; see exact verdicts and scope." if key == "au" else
                                "Candidate review saved; consult Auditor verdicts if available."})

    used = sum(len(json.loads(r["output"]).get("tool_calls", [])) for r in triage)
    used += sum(run["tool_calls"] for run in coordinator)
    total = 12 * len(triage) + sum(run["request"]["limits"]["max_tool_calls"] for run in coordinator)

    # Everything a decision touches, once the proposals and findings both exist.
    _link_approvals(tasks, task_approvals)
    _note_decisions_on_findings(findings, approval_rows)
    # A person's own decisions are the log's most important entries, so they land
    # after the agents' — the run happened first, the decision on it came later.
    decisions.extend(human_decisions)

    workflows = [_coordinator_workflow(run) for run in coordinator]
    comparisons, gate = approvals_module.comparisons(approval_rows, findings)
    report = _report(cov, findings, coordinator, comparisons, gate)
    waiting = sum(1 for a in approval_rows if a["status"] == "pending")
    actions = []
    if findings:
        actions.append({"label": "Review findings", "href": "findings", "primary": True})
    if waiting:
        actions.insert(0, {"label": f"Decide {waiting} proposal(s)", "href": "approvals", "primary": True})
        for action in actions[1:]:
            action["primary"] = False
    if report["markdown"]:
        actions.append({"label": "Open the report", "href": "reports", "primary": not actions})

    return {
        "contract_version": 2,
        "workspace": {
            "id": ws, "name": w["name"], "kind": w["kind"], "period": f"{w['start']} — {w['end']}",
            "mode": "live" if (triage_run or coordinator) else "not_started",
            "snapshot_id": snapshot_id or "No committed records",
            "disabled_tabs": _disabled_tabs(w),
            "model": triage_run["model"] if triage_run else (reported["model_label"] if reported else "Not configured"),
            "run_budget": {"used": used, "total": total},
            "intake": True, "currency": w["currency"], "profile": w["profile"],
        },
        "agents": agents,
        "briefing": {
            "generated_at": generated_at,
            "text": briefing_text or "Upload records and review source coverage. Agent investigations have not run.",
            "actions": actions,
        },
        "kpis": _kpis(cov, findings, triage, coordinator),
        "workflows": workflows, "tasks": tasks, "findings": findings, "approvals": approval_rows,
        "decisions": decisions,
        # Owned by the Learning workstream; this layer must keep emitting them unchanged.
        "playbooks": [], "ablation": None,
        "report": report,
    }
