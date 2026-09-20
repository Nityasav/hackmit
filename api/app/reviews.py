"""Unified snapshot reviews, human follow-up and a reproducible fictional demo."""
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from . import db, ingestion
from .accounting.review import checks
from .cfo.api import runtime

router = APIRouter(prefix="/api", tags=["Director review"])
ACTIVE = {"queued", "planning", "running"}
LIMITATIONS = [
    "Supplied records only; no assurance of completeness, fraud determination or audit opinion.",
    "USD fictional management profile, not an Ontario/TDSB statutory accounting adapter.",
    "Amounts can overlap across checks. Do not add them together or call them savings.",
    "Human decisions are proposals and follow-up records. No ledger, payment or grant submission is changed.",
]


def current_snapshot(c, ws):
    ingestion.workspace(c, ws)
    row = c.execute("SELECT id FROM snapshots WHERE ws=? ORDER BY revision DESC LIMIT 1", (ws,)).fetchone()
    return row[0] if row else None


def scan(ws):
    # Read inputs, calculate and persist under the same transaction as commit.
    with db.connect() as c:
        config = ingestion.workspace(c, ws)
        snapshot = current_snapshot(c, ws)
        if not snapshot:
            raise HTTPException(409, "Commit source records before scanning.")
        if config["kind"] != "synthetic" or config["currency"] != "USD":
            raise HTTPException(409, "Transaction checks require the fictional USD management profile.")
        rows = ingestion.active_records(c, ws)
        found = checks(rows, config)
        payload = dict(id=db.uid("scan"), workspace=ws, snapshot_id=snapshot, created_at=db.now(),
                       checks=found, record_count=len(rows), method="deterministic", limitations=LIMITATIONS)
        c.execute("INSERT INTO review_scans VALUES (?,?,?,?,?)", (payload["id"], ws, snapshot, payload["created_at"], db.encode(payload)))
        db.event(c, ws, "review.scan", {"scan_id": payload["id"], "snapshot_id": snapshot, "checks": len(found)})
        return payload


@router.post("/workspaces/{ws}/review/scans", status_code=201)
def start_scan(ws: str):
    return scan(ws)


@router.get("/workspaces/{ws}/review")
def review(ws: str, request: Request):
    with db.connect() as c:
        config = ingestion.workspace(c, ws)
        snapshot = current_snapshot(c, ws)
        scans = [json.loads(r[0]) for r in c.execute("SELECT payload FROM review_scans WHERE ws=? ORDER BY rowid DESC LIMIT 2", (ws,))]
        actions = [json.loads(r[0]) | {"snapshot_id": r[1]} for r in c.execute("SELECT payload,snapshot_id FROM review_actions WHERE ws=?", (ws,))]
        history = [dict(r) | {"payload": json.loads(r["payload"])} for r in c.execute("SELECT * FROM events WHERE ws=? AND kind LIKE 'review.%' ORDER BY rowid DESC LIMIT 100", (ws,))]
        demo = c.execute("SELECT evidence_added FROM demo_sessions WHERE ws=?", (ws,)).fetchone()
        standalone = [dict(row) for agent in ("cfo", "grants_compliance") if (row := c.execute(
            "SELECT * FROM agent_runs WHERE ws=? AND agent=? AND status='completed' ORDER BY created_at DESC LIMIT 1", (ws, agent)).fetchone())]
        audit_rows = c.execute("SELECT output FROM agent_runs WHERE ws=? AND agent='internal_auditor' AND status='completed' ORDER BY created_at DESC LIMIT 20", (ws,)).fetchall()
    latest = runtime(request).repository.latest(ws)
    live = latest.model_dump() if latest else None
    findings = []
    if scans:
        findings.extend(dict(item, snapshot_id=scans[0]["snapshot_id"], stale=scans[0]["snapshot_id"] != snapshot) for item in scans[0]["checks"])
    verdicts = {}
    for row in audit_rows:
        for verdict in json.loads(row[0]).get("analysis", {}).get("reviews", []):
            verdicts.setdefault(verdict["finding_id"], verdict)
    for saved in standalone:
        for i, candidate in enumerate(json.loads(saved["output"]).get("analysis", {}).get("findings", []), 1):
            identifier = f"{saved['id']}-finding-{i}"
            verdict = verdicts.get(identifier)
            findings.append(dict(id=identifier, title=candidate["title"], role="cfo" if saved["agent"] == "cfo" else "gr",
                status="attention", explanation=candidate["summary"], amount_cents=None,
                action="Review the candidate and its exact sources; no independently confirmed amount is asserted here.",
                origin="standalone_candidate", review=(f"Bounded Auditor verdict: {verdict['verdict']} — {verdict['rationale']}" if verdict else "Independent review pending. This is a candidate, not a verified financial conclusion."),
                evidence=[dict(source_id=e["source_id"], line=e["line"]) for e in candidate.get("citations", [])],
                snapshot_id=saved["snapshot_id"], stale=saved["snapshot_id"] != snapshot))
    if latest and latest.scope:
        # Never surface intermediate acceptances as a completed report.
        if latest.status not in ACTIVE | {"failed", "interrupted", "stale"}:
            for accepted in latest.accepted:
                claim = accepted.claim
                findings.append(dict(id=latest.id + ":" + claim.id, title=claim.title, role=accepted.role,
                    status="pass" if claim.disposition == "cleared" else "attention", explanation=claim.conclusion,
                    amount_cents=accepted.calculation.amount_cents if accepted.calculation else None,
                    action=claim.proposed_action, origin="live_agent", review=accepted.review.rationale,
                    evidence=[dict(source_id=s, line=1) for s in claim.evidence_ids],
                    snapshot_id=latest.scope.snapshot_id, stale=latest.scope.snapshot_id != snapshot))
    for item in findings:
        item["follow_up"] = next((a for a in actions if a["finding_id"] == item["id"] and a["snapshot_id"] == item["snapshot_id"]), None)
    prior = {i["id"]: i for i in scans[1]["checks"]} if len(scans) > 1 else {}
    changes = [dict(id=i["id"], title=i["title"], before=prior[i["id"]]["explanation"], after=i["explanation"])
               for i in scans[0]["checks"] if i["id"] in prior and (i["status"], i["amount_cents"], i["explanation"]) != (prior[i["id"]]["status"], prior[i["id"]]["amount_cents"], prior[i["id"]]["explanation"])] if scans else []
    return dict(workspace=config, snapshot_id=snapshot, scan=scans[0] if scans else None, live=live,
                live_stale=bool(latest and latest.scope and latest.scope.snapshot_id != snapshot),
                findings=findings, changes=changes, history=history, limitations=LIMITATIONS,
                demo=demo is not None, evidence_added=bool(demo and demo[0]))


def markdown(view):
    def plain(value):
        # Keep model/source Markdown from introducing links or active HTML in exports.
        return str(value).replace("<", "&lt;").replace(">", "&gt;").replace("[", "\\[").replace("]", "\\]")
    lines = ["# SchoolTrace director briefing", "", plain(view["workspace"]["name"]),
             f"Period: {view['workspace']['start']} to {view['workspace']['end']}",
             f"Current snapshot: {view['snapshot_id']}", "", "## Method",
             "Rules-based record checks, with any live Auditor-accepted claims separately labelled. Not an audit opinion."]
    if not view["scan"] and not view["live"]:
        lines += ["No investigation has run. No assurance is implied."]
    for f in view["findings"]:
        cents = f["amount_cents"]
        amount = "Not established" if cents is None else f"{'-' if cents < 0 else ''}USD {abs(cents) // 100:,}.{abs(cents) % 100:02d}"
        lines += ["", "## " + plain(f["title"]), f"Status: {f['status']}; method: {f['origin']}; snapshot: {f['snapshot_id']}",
                  "HISTORICAL / RERUN REQUIRED" if f["stale"] else "Current snapshot", plain(f["explanation"]),
                  f"Check amount: {amount}. Amounts may overlap and are not savings.", "Next step: " + plain(f["action"]),
                  "Evidence: " + ("; ".join(f"{e['source_id']} line {e['line']}" for e in f["evidence"]) or "Missing input")]
        action = f["follow_up"]
        lines += ["Human follow-up: " + (plain(f"{action['status']}; {action['owner']}; {action['note']}") if action else "Not recorded for this snapshot")]
    if view["live"]:
        lines += ["", "## Live investigation", "Status: " + view["live"]["status"],
                  "HISTORICAL SNAPSHOT" if view["live_stale"] else "Current snapshot", plain(view["live"]["briefing"]),
                  *["- Unresolved: " + plain(x) for x in view["live"]["unresolved"]]]
    lines += ["", "## Follow-up history (last hundred events)"]
    for e in view["history"]:
        lines.append(plain(f"- {e['created_at']} · {e['actor']} · {e['kind']} · {e['payload'].get('status', '')} · {e['payload'].get('note', '')}"))
    lines += ["", "## Limitations", *["- " + x for x in LIMITATIONS]]
    return "\n".join(lines)


@router.get("/workspaces/{ws}/review/report", response_class=PlainTextResponse)
def export_report(ws: str, request: Request):
    return PlainTextResponse(markdown(review(ws, request)), media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="schooltrace-director-briefing.md"', "Cache-Control": "no-store"})


class FollowUp(BaseModel):
    snapshot_id: str
    finding_id: str = Field(min_length=1, max_length=200)
    expected_version: int = Field(ge=0)
    owner: str = Field(default="", max_length=120)
    status: Literal["open", "evidence_requested", "proposed", "approved_proposal", "rejected_proposal"] = "open"
    note: str = Field(min_length=1, max_length=2000)


@router.post("/workspaces/{ws}/review/actions")
def act(ws: str, body: FollowUp, request: Request):
    view = review(ws, request)
    finding = next((f for f in view["findings"] if f["id"] == body.finding_id and f["snapshot_id"] == body.snapshot_id and not f["stale"]), None)
    if not finding:
        raise HTTPException(409, "Finding is unavailable or outdated. Rerun against the current snapshot.")
    actor = getattr(request.state, "user", {"name": "local-reviewer", "role": "admin"})
    if body.status in {"approved_proposal", "rejected_proposal"} and actor["role"] not in {"admin", "reviewer"}:
        raise HTTPException(403, "Reviewer role required for a proposal decision.")
    with db.connect() as c:
        if current_snapshot(c, ws) != body.snapshot_id:
            raise HTTPException(409, "Snapshot changed. Refresh and rerun.")
        old = c.execute("SELECT version,payload FROM review_actions WHERE ws=? AND snapshot_id=? AND finding_id=?", (ws, body.snapshot_id, body.finding_id)).fetchone()
        if (old[0] if old else 0) != body.expected_version:
            raise HTTPException(409, "Another reviewer updated this item. Refresh first.")
        if body.status in {"approved_proposal", "rejected_proposal"} and (not old or json.loads(old[1])["status"] != "proposed"):
            raise HTTPException(409, "Record a proposal before deciding it.")
        payload = body.model_dump() | dict(version=body.expected_version + 1, at=db.now(), actor=actor["name"])
        c.execute("INSERT INTO review_actions VALUES (?,?,?,?,?) ON CONFLICT(ws,snapshot_id,finding_id) DO UPDATE SET version=excluded.version,payload=excluded.payload",
                  (ws, body.snapshot_id, body.finding_id, payload["version"], db.encode(payload)))
        if body.status == "evidence_requested":
            c.execute("INSERT INTO evidence_requests (id,ws,title,role,task_id) VALUES (?,?,?,?,?)",
                      (db.uid("request"), ws, body.note[:300], "document", body.finding_id))
        db.event(c, ws, "review.follow_up", payload, actor["name"])
    return payload


def demo_files():
    sample = json.loads((Path(__file__).resolve().parents[2] / "contracts/fixtures/intake.json").read_text())
    files = [f for f in sample["files"] if not f.get("later")]
    files += [dict(name="invoices.csv", role="invoice", content="record_id,vendor_id,invoice_number,service_date,amount,po_id,receipt_id\nINV-1,VENDOR-1,A-101,2026-09-10,1200.00,PO-1,\nINV-2,VENDOR-1,A-101,2026-09-10,1200.00,PO-1,\nINV-3,VENDOR-2,A-101,2026-09-10,1200.00,PO-2,REC-2\n"),
              dict(name="budget.csv", role="budget", content="record_id,account,amount,approval_reference\nBUD-1,5000,9000.00,BOARD-DEMO-SEP\n")]
    return files, next(f for f in sample["files"] if f.get("later"))


def import_files(ws, files):
    batch = ingestion.stage(ws, [(f["name"], f["content"].encode(), ingestion.FileOptions(role=f["role"])) for f in files])
    return ingestion.commit(ws, batch["id"], ingestion.CommitRequest(expected_version=batch["version"], idempotency_key=batch["id"]))


@router.post("/review-demo", status_code=201)
def create_demo():
    ws = ingestion.create_workspace(ingestion.WorkspaceCreate(name="Maplebridge · judge demo", start="2026-09-01", end="2026-09-30",
        scope="Fictional management review: duplicate candidates, budget variance, payroll and grant support."))["id"]
    files, _ = demo_files()
    import_files(ws, files)
    with db.connect() as c:
        c.execute("INSERT INTO demo_sessions(ws) VALUES (?)", (ws,))
    return {"workspace": ws, "scan": scan(ws)}


@router.post("/workspaces/{ws}/review/demo-evidence")
def add_demo_evidence(ws: str):
    with db.connect() as c:
        row = c.execute("SELECT evidence_added FROM demo_sessions WHERE ws=?", (ws,)).fetchone()
        if not row:
            raise HTTPException(409, "This action is only for the generated fictional demo.")
        if row[0]:
            return {"already_added": True}
    _, evidence = demo_files()
    imported = import_files(ws, [evidence])
    with db.connect() as c:
        c.execute("UPDATE demo_sessions SET evidence_added=1 WHERE ws=?", (ws,))
        db.event(c, ws, "review.demo_evidence", {"snapshot_id": imported["snapshot_id"]})
    return imported


class DeleteWorkspace(BaseModel):
    confirmation: str


@router.delete("/workspaces/{ws}")
def delete_workspace(ws: str, body: DeleteWorkspace, request: Request):
    # Prevent a coordinator run starting between the active check and deletion.
    with runtime(request).mutation_lock:
        return _delete_workspace(ws, body, request)


def _delete_workspace(ws: str, body: DeleteWorkspace, request: Request):
    if request.state.user["role"] != "admin":
        raise HTTPException(403, "Admin role required.")
    if body.confirmation != ws:
        raise HTTPException(422, "Confirm the exact workspace ID.")
    rt = runtime(request)
    if ws in rt.active_workspaces:
        raise HTTPException(409, "Wait for the active investigation before deleting.")
    with db.connect() as c:
        ingestion.workspace(c, ws)
        if c.execute("SELECT 1 FROM agent_runs WHERE ws=? AND status='running'", (ws,)).fetchone():
            raise HTTPException(409, "Wait for the active standalone review before deleting.")
        c.execute("ATTACH DATABASE ? AS cfo_history", (rt.repository.path,))
        c.execute("DELETE FROM cfo_history.cfo_runs WHERE workspace=?", (ws,))
        for table in ("review_actions", "review_scans", "demo_sessions", "agent_requests", "agent_runs", "evidence_requests", "records", "snapshots", "sources", "batches", "events"):
            c.execute(f"DELETE FROM {table} WHERE ws=?", (ws,))
        c.execute("DELETE FROM workspaces WHERE id=?", (ws,))
    return {"deleted": ws, "note": "Logical deletion completed. OS backups and recoverable filesystem remnants are outside this operation."}
