"""Immutable task outputs. Reading or exporting never starts another agent."""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from .. import db, ingestion
from .registry import AGENTS

router = APIRouter(prefix="/api/workspaces/{ws}/agents/deliverables")


@router.get("/{decision_id}")
def deliverable(ws: str, decision_id: str):
    with db.connect() as c:
        workspace = ingestion.workspace(c, ws)
        row = c.execute("SELECT * FROM agent_decisions WHERE ws=? AND id=?", (ws, decision_id)).fetchone()
        if not row:
            raise HTTPException(404, "Task output not found in this workspace.")
        decision = dict(row)
        event = c.execute("SELECT payload FROM events WHERE ws=? AND kind='agent.deliverable' "
                          "AND json_extract(payload,'$.decision_id')=? ORDER BY rowid DESC LIMIT 1",
                          (ws, decision_id)).fetchone()
        stored = json.loads(event[0]) if event else {}
        snapshot_id = stored.get("snapshot_id")
        if not snapshot_id:
            origin = c.execute("SELECT payload FROM events WHERE ws=? AND kind='agent.decision_snapshot' "
                               "AND json_extract(payload,'$.decision_id')=? LIMIT 1", (ws, decision_id)).fetchone()
            snapshot_id = json.loads(origin[0])["snapshot_id"] if origin else None
        snapshot = c.execute("SELECT manifest FROM snapshots WHERE ws=? AND id=?", (ws, snapshot_id)).fetchone()
        current = c.execute("SELECT id FROM snapshots WHERE ws=? ORDER BY revision DESC LIMIT 1", (ws,)).fetchone()
        objective = stored.get("objective")
        if not objective:
            turn = c.execute("SELECT body FROM conversations WHERE ws=? AND thread_id=? AND role='person' "
                             "AND created_at<=? ORDER BY rowid DESC LIMIT 1",
                             (ws, decision["thread_id"], decision["created_at"])).fetchone()
            objective = json.loads(turn[0]).get("text") if turn else None
        output = stored.get("output") or {}
        result = output.get("result") or {
            "summary": decision["summary"], "rationale": decision["why"],
            "disposition": decision["action"].split(":")[-1].strip(),
            "proposed_action": "Not recorded for this older task.",
            "exceptions": [], "open_questions": [],
        }
        evidence = json.loads(decision["evidence"] or "[]")
        record_ids = set(json.loads(snapshot[0])["record_ids"]) if snapshot else set()
        # Resolve record keys only against this task's immutable snapshot.
        records = [dict(r) for r in c.execute("SELECT id,role,record_key,source_id,locator FROM records WHERE ws=?", (ws,)) if r["id"] in record_ids]
        sources = {r["id"]: r["name"] for r in c.execute("SELECT id,name FROM sources WHERE ws=?", (ws,))}
        resolved = []
        for citation in evidence:
            matches = [r for r in records if r["role"] == citation.get("role") and r["record_key"] == citation.get("record_key")]
            if not citation.get("source_id") and len(matches) == 1:
                citation = {**citation, "source_id": matches[0]["source_id"], "line": matches[0]["locator"]}
            resolved.append({**citation, "source_name": sources.get(citation.get("source_id"), "")})
        approvals = [dict(r) for r in c.execute("SELECT status,decided_at FROM approvals WHERE ws=? AND finding_id=?", (ws, decision_id))]
    return {
        "id": decision_id, "agent_id": decision["agent"],
        "agent_name": AGENTS[decision["agent"]].name if decision["agent"] in AGENTS else decision["agent"],
        "created_at": decision["created_at"], "thread_id": decision["thread_id"],
        "objective": objective, "legacy": not bool(event), "snapshot_id": snapshot_id,
        "stale": not current or snapshot_id != current[0], "workspace": workspace,
        "result": result, "evidence": resolved, "calculations": output.get("calculations", {}),
        "memory_context": stored.get("memory_context", []),
        "escalated": bool(decision["escalated"]), "approvals": approvals,
        "review": f"{decision['reviewer']}: {decision['review_verdict']}" if decision["reviewer"] else "Not independently reviewed.",
    }


@router.get("/{decision_id}/pdf")
def pdf(ws: str, decision_id: str):
    from ..briefing_pdf import render
    data = deliverable(ws, decision_id)
    result = data["result"]
    finding = {"title": data["agent_name"], "role": data["agent_id"], "role_label": data["agent_name"],
               "status": "gap" if result.get("disposition") == "insufficient_evidence" else "attention" if data["escalated"] or result.get("exceptions") else "pass",
               "origin": "agent", "stale": data["stale"], "explanation": result.get("summary", ""),
               "amount_cents": None, "action": result.get("proposed_action", "Not recorded."),
               "review": data["review"], "evidence": data["evidence"], "follow_up": None,
               "rationale": result.get("rationale", ""), "exceptions": result.get("exceptions", []),
               "open_questions": result.get("open_questions", [])}
    view = {"workspace": data["workspace"], "snapshot_id": data["snapshot_id"],
            "report_title": data["agent_name"] + " - task report", "objective": data["objective"] or "Original request was not saved for this older task.",
            "task_created_at": data["created_at"], "findings": [finding], "history": [],
            "limitations": ["Recorded task output, not a fresh analysis or audit opinion.", data["review"],
                            "Approving a conclusion does not post entries, pay money or verify missing evidence."]}
    return Response(render(view), media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="sherlock-{data["agent_id"]}-{decision_id}.pdf"',
        "Cache-Control": "no-store"})
