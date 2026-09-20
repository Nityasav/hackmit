"""Run-scoped audit deliverables, assembled from recorded work, never invented totals."""
import json
from collections import Counter

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from .. import db, ingestion
from ..reviews import role_label
from .deliverables import deliverable
from .registry import AGENTS

router = APIRouter(prefix="/api/workspaces/{ws}/audit-reports", tags=["Audit deliverables"])


@router.get("/{thread_id}")
def report(ws: str, thread_id: str):
    with db.connect() as c:
        config = ingestion.workspace(c, ws)
        turns = [dict(r) for r in c.execute("SELECT * FROM conversations WHERE ws=? AND thread_id=? ORDER BY rowid", (ws, thread_id))]
        asked = next((r for r in reversed(turns) if r["role"] == "person"), None)
        answer = next((r for r in reversed(turns) if r["role"] == "orchestrator"), None)
        if not asked or not answer:
            raise HTTPException(404, "Audit run not found in this workspace.")
        request = json.loads(asked["body"])
        # Previous versions recorded the expanded full-review request but not its flag.
        legacy = "full_review" not in request
        if not request.get("full_review") and not (legacy and request.get("text", "").startswith("Review all domains:")):
            raise HTTPException(404, "This conversation was not a Financial Audit run.")
        if answer["status"] == "running":
            raise HTTPException(409, "The review is still running; a report is not ready yet.")
        body = json.loads(answer["body"])
        scan_row = c.execute("SELECT payload FROM review_scans WHERE ws=? AND id=?", (ws, request.get("scan_id"))).fetchone()
        scan = json.loads(scan_row[0]) if scan_row else None
        decisions = [dict(r) for r in c.execute("SELECT * FROM agent_decisions WHERE ws=? AND thread_id=? AND created_at>=? ORDER BY rowid", (ws, thread_id, asked["created_at"]))]
        pending = c.execute("SELECT count(DISTINCT finding_id) FROM approvals WHERE ws=? AND run_id=? AND status='pending'", (ws, thread_id)).fetchone()[0]
        current = c.execute("SELECT id FROM snapshots WHERE ws=? ORDER BY revision DESC LIMIT 1", (ws,)).fetchone()
        sources = {r["id"]: r["name"] for r in c.execute("SELECT id,name FROM sources WHERE ws=?", (ws,))}
    outputs = [deliverable(ws, d["id"]) for d in decisions]
    snapshot = request.get("snapshot_id")
    if not snapshot:
        snapshots = {d["snapshot_id"] for d in outputs if d["snapshot_id"]}
        snapshot = next(iter(snapshots)) if len(snapshots) == 1 else None
    stale = not snapshot or not current or snapshot != current[0]
    findings = [dict(f, stale=stale, role_label=role_label(f["role"]),
                     evidence=[dict(e, source_name=sources.get(e.get("source_id"), "")) for e in f["evidence"]])
                for f in (scan or {}).get("checks", [])]
    for output in outputs:
        result = output["result"]
        disposition = result.get("disposition")
        status = "gap" if disposition == "insufficient_evidence" or "needs_evidence" in output["review"] else "attention" if output["escalated"] or disposition == "exception" or "reject" in output["review"] else "pass" if disposition == "clear" else "gap"
        findings.append({"id": output["id"], "title": output["agent_name"], "role": output["agent_id"],
            "role_label": output["agent_name"], "status": status, "origin": "agent", "stale": output["stale"],
            "explanation": result.get("summary", ""), "rationale": result.get("rationale", ""),
            "action": result.get("proposed_action", "Review the cited evidence."), "amount_cents": None,
            "review": output["review"], "evidence": output["evidence"], "follow_up": None,
            "exceptions": result.get("exceptions", []), "open_questions": result.get("open_questions", [])})
    findings.sort(key=lambda f: {"attention": 0, "gap": 1, "pass": 2}.get(f["status"], 1))
    # Reviewers may execute without writing a second task conclusion. Count that work
    # separately; never call it a separate financial finding.
    contributed = {d["agent"] for d in decisions} | {d["reviewer"] for d in decisions if d["reviewer"]}
    domains = []
    for worker in ("A", "B", "C", "D"):
        specialists = [key for key, spec in AGENTS.items() if spec.tier == "subagent" and key.startswith(worker)]
        missing = [AGENTS[key].name for key in specialists if key not in contributed]
        domains.append({"id": worker, "name": AGENTS[worker].name, "recorded": len(specialists) - len(missing),
                        "total": len(specialists), "not_assessed": missing})
    counts = Counter(f["status"] for f in findings)
    unresolved = list(body.get("unresolved") or [])
    if answer["status"] == "failed":
        unresolved.insert(0, body.get("text") or "The run stopped before completing its planned work.")
    if legacy:
        unresolved.append("Older run: its exact record-check scan was not saved with the conversation; unrelated scans are excluded.")
    if any(o["snapshot_id"] != snapshot for o in outputs):
        unresolved.append("Some task snapshots differ or are unknown. Verify the cited books before combining these conclusions.")
    not_assessed = sum(len(d["not_assessed"]) for d in domains)
    if answer["status"] == "failed":
        headline = "Review stopped — partial results only"
    elif answer["status"] == "waiting_on_you" or pending:
        headline = "Waiting for human decisions — review incomplete"
    elif counts["attention"]:
        headline = "Items require attention"
    elif counts["gap"] or unresolved or not_assessed:
        headline = "Evidence or coverage gaps remain"
    else:
        headline = "No exceptions reported in the assessed scope"
    summary = (f"{len(outputs)} agent conclusions and {len((scan or {}).get('checks', []))} record checks were recorded. "
               f"{counts['attention']} items need attention; {counts['gap']} results have evidence gaps. "
               f"{not_assessed} specialist areas have no recorded contribution; {pending} decisions remain pending. "
               "This describes the supplied records, not assurance of the company's overall financial health.")
    return {"thread_id": thread_id, "status": answer["status"], "created_at": asked["created_at"],
        "workspace": request.get("workspace_at_run") or config, "snapshot_id": snapshot, "stale": stale,
        "legacy": legacy, "headline": headline, "executive_summary": summary,
        "objective": request.get("text", ""), "domains": domains, "unresolved": unresolved,
        "counts": {"attention": counts["attention"], "gap": counts["gap"], "pass": counts["pass"],
                   "conclusions": len(outputs), "pending": pending}, "findings": findings,
        "scan": scan, "history": [], "limitations": [
            "Automated financial review of supplied books, not a certified audit or independent audit opinion.",
            "Amounts may overlap; do not add check amounts together or call them savings or losses.",
            "Unassessed areas are not clear. Human approval does not create missing evidence or post transactions.",
            *( ["Historical report: the current books differ or the original snapshot is unknown."] if stale else [])]}


@router.get("/{thread_id}/pdf")
def export(ws: str, thread_id: str):
    from ..briefing_pdf import render
    data = report(ws, thread_id)
    view = {**data, "report_title": "Financial audit review", "objective": None,
            "include_historical_counts": True,
            "audit_summary": data["headline"] + ". " + data["executive_summary"],
            "audit_domains": data["domains"], "audit_gaps": data["unresolved"]}
    return Response(render(view), media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="sherlock-financial-audit.pdf"', "Cache-Control": "no-store"})
