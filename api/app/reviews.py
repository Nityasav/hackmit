"""Unified snapshot reviews over committed records, plus human follow-up."""
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from . import db, ingestion
from .accounting.controls import checks

router = APIRouter(prefix="/api", tags=["Director review"])
LIMITATIONS = [
    "Supplied records only; no assurance of completeness, fraud determination or audit opinion.",
    "USD accrual profile for a single operating entity; not a statutory or consolidated adapter.",
    "Amounts can overlap across checks. Do not add them together or call them savings.",
    "Human decisions are proposals and follow-up records. No ledger, payment or grant submission is changed.",
]


def describe_event(entry: dict) -> str:
    """One plain sentence saying what a person or a scan actually did.

    The history listed an event kind, an actor and a timestamp — `review.scan`,
    `approval_decided` — which says that something happened without saying
    what. Anyone reading back through a period has to reconstruct it from the
    payload, and the export was worse: it printed a status and a note that most
    kinds do not carry, so most lines read as a date and two empty fields.
    """
    payload = entry.get("payload") or {}
    actor = entry.get("actor") or "someone"
    kind = entry.get("kind") or ""

    if kind == "approval_decided":
        verdict = payload.get("decision", "decided")
        target = payload.get("finding_id") or payload.get("approval_id") or "a proposal"
        applied = payload.get("applied")
        tail = ("The proposed entries were posted." if applied else
                "Nothing was posted, paid or approved in the books; the decision was recorded "
                "and became precedent the next run has to re-check.")
        return f"{actor} {verdict} the agent conclusion {target}. {tail}"

    if kind == "review.follow_up":
        status = str(payload.get("status", "")).replace("_", " ") or "recorded a follow-up on"
        owner = payload.get("owner")
        note = (payload.get("note") or "").strip()
        parts = [f"{actor} marked {payload.get('finding_id', 'a finding')} as {status}"]
        if owner:
            parts.append(f"owned by {owner}")
        line = ", ".join(parts) + "."
        return f"{line} {note}".strip()

    if kind == "review.scan":
        checks = payload.get("checks", 0)
        return (f"{actor} ran the rules-based record checks over snapshot "
                f"{payload.get('snapshot_id', 'the current one')}, producing {checks} check(s). "
                "No model was called and nothing was changed.")

    return f"{actor} · {kind}"


def event_agent(entry: dict, raisers: dict[str, str]) -> str | None:
    """Which agent raised what a person acted on, or None for a scan.

    A record check is nobody's conclusion — it is arithmetic over the rows —
    so it has no agent, and saying so is more useful than attributing it to
    one.
    """
    payload = entry.get("payload") or {}
    if payload.get("agent"):
        return payload["agent"]
    for key in ("approval_id", "finding_id", "task_id"):
        found = raisers.get(payload.get(key) or "")
        if found:
            return found
    return None


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
            raise HTTPException(409, "Transaction checks require the USD accrual profile.")
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
        # Approving or rejecting what an agent escalated is human follow-up —
        # arguably the only kind that changes what the agents do next — but it
        # is recorded as `approval_decided`, so a history filtered to
        # `review.%` showed everything except the decisions people actually
        # made. They were in the table the whole time, filtered out on read.
        history = [dict(r) | {"payload": json.loads(r["payload"])} for r in c.execute(
            "SELECT * FROM events WHERE ws=? AND (kind LIKE 'review.%' OR kind='approval_decided')"
            " ORDER BY rowid DESC LIMIT 100", (ws,))]
        # Which agent raised the thing a person acted on. Newer approval events
        # carry it; older ones and follow-ups are resolved from the proposal or
        # the decision trail, so the whole history can be filtered by agent and
        # not just the part recorded since.
        raisers = {row["id"]: row["agent"] for row in c.execute(
            "SELECT id, agent FROM approvals WHERE ws=?", (ws,))}
        raisers |= {row["id"]: row["agent"] for row in c.execute(
            "SELECT id, agent FROM agent_decisions WHERE ws=?", (ws,))}
        history = [entry | {"summary": describe_event(entry),
                            "agent": event_agent(entry, raisers)} for entry in history]
        # Agent conclusions now live in `agent_decisions`, written by the graph.
        decisions = [dict(row) for row in c.execute(
            "SELECT * FROM agent_decisions WHERE ws=? ORDER BY rowid DESC LIMIT 50", (ws,))]
    findings = []
    if scans:
        findings.extend(dict(item, snapshot_id=scans[0]["snapshot_id"],
                             stale=scans[0]["snapshot_id"] != snapshot)
                        for item in scans[0]["checks"])
    # What the agents concluded, read from the decision trail they wrote as they worked.
    # An escalated decision needs attention whatever the agent called it, because the
    # threshold that escalated it is the workspace's and not the agent's.
    for decision in decisions:
        reviewed = decision["reviewer"]
        findings.append(dict(
            id=decision["id"], title=decision["action"], role=decision["agent"],
            status="attention" if decision["escalated"] else "pass",
            explanation=decision["summary"], amount_cents=None,
            action=decision["why"] or "Review the cited evidence.",
            origin="agent",
            review=("Reviewed by " + str(reviewed) + ": " + str(decision["review_verdict"]))
            if reviewed else
            ("Independent review pending. This is an agent conclusion, not a verified "
             "financial result."),
            evidence=[dict(source_id=e.get("source_id", ""), line=e.get("line") or 1)
                      for e in json.loads(decision["evidence"] or "[]")],
            confidence=decision["confidence"],
            snapshot_id=snapshot, stale=False))
    live = {"decisions": len(decisions),
            "escalated": sum(1 for d in decisions if d["escalated"]),
            "spend_cents": sum(d["cost_cents"] for d in decisions)} if decisions else None
    for item in findings:
        item["follow_up"] = next((a for a in actions if a["finding_id"] == item["id"] and a["snapshot_id"] == item["snapshot_id"]), None)
    prior = {i["id"]: i for i in scans[1]["checks"]} if len(scans) > 1 else {}
    changes = [dict(id=i["id"], title=i["title"], before=prior[i["id"]]["explanation"], after=i["explanation"])
               for i in scans[0]["checks"] if i["id"] in prior and (i["status"], i["amount_cents"], i["explanation"]) != (prior[i["id"]]["status"], prior[i["id"]]["amount_cents"], prior[i["id"]]["explanation"])] if scans else []
    return dict(workspace=config, snapshot_id=snapshot, scan=scans[0] if scans else None,
                live=live, live_stale=False,
                findings=findings, changes=changes, history=history, limitations=LIMITATIONS)


def markdown(view):
    def plain(value):
        # Keep model/source Markdown from introducing links or active HTML in exports.
        return str(value).replace("<", "&lt;").replace(">", "&gt;").replace("[", "\\[").replace("]", "\\]")
    lines = ["# Sherlock director briefing", "", plain(view["workspace"]["name"]),
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
        # A tally off the decision trail. This used to read `status`, `briefing`
        # and `unresolved` from a coordinator run object; that coordinator was
        # removed, and those keys with it, so exporting a briefing for any
        # workspace an agent had run raised KeyError.
        live = view["live"]
        lines += ["", "## Live agent review",
                  "HISTORICAL SNAPSHOT" if view["live_stale"] else "Current snapshot",
                  f"{live['decisions']} agent conclusion(s), {live['escalated']} escalated to a person.",
                  "Each conclusion is listed above with its evidence. No approval, "
                  "posting or payment was made."]
    lines += ["", "## Follow-up history (last hundred events)"]
    for e in view["history"]:
        lines.append(plain(f"- {e['created_at']} · {e.get('summary') or e['kind']}"))
    lines += ["", "## Limitations", *["- " + x for x in LIMITATIONS]]
    return "\n".join(lines)


@router.get("/workspaces/{ws}/review/report", response_class=PlainTextResponse)
def export_report(ws: str, request: Request):
    return PlainTextResponse(markdown(review(ws, request)), media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="sherlock-director-briefing.md"', "Cache-Control": "no-store"})


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


class DeleteWorkspace(BaseModel):
    confirmation: str


@router.delete("/workspaces/{ws}")
def delete_workspace(ws: str, body: DeleteWorkspace, request: Request):
    if request.state.user["role"] != "admin":
        raise HTTPException(403, "Admin role required.")
    if body.confirmation != ws:
        raise HTTPException(422, "Confirm the exact workspace ID.")
    with db.connect() as c:
        ingestion.workspace(c, ws)
        for row in c.execute("SELECT payload FROM extraction_items WHERE ws=? AND kind='benchmark_job'", (ws,)):
            if json.loads(row[0]).get("status") in {"queued", "running"}:
                raise HTTPException(409, "Wait for the extraction benchmark before deleting.")
        # Children before parents: decisions and links reference the events, and the
        # events reference the workspace.
        for table in ("extraction_active", "extraction_items", "extraction_documents",
                      "review_actions", "review_scans", "agent_decisions", "links",
                      "economic_events", "agent_requests", "agent_runs",
                      "evidence_requests", "approvals", "precedents", "records",
                      "snapshots", "sources", "batches", "events"):
            c.execute(f"DELETE FROM {table} WHERE ws=?", (ws,))
        c.execute("DELETE FROM workspaces WHERE id=?", (ws,))
    return {"deleted": ws, "note": "Logical deletion completed. OS backups and recoverable filesystem remnants are outside this operation."}
