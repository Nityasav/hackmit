"""Proposals agents make, and the decisions only a human may take.

Two rules shape this module.

**Agents propose, humans decide.** Nothing here lets an agent set a status. The
only transition out of `pending` runs through `decide`, which records who did it
and when.

**A proposal may only contain amounts the engine produced.** An agent's
`proposed_action` is prose, and prose is not a journal. A journal may only come
from a deterministic calculation, and only from a claim that survived independent
review — which is what `store()` refuses without.

Proposals are written by whatever raises them; phase 4 routes an escalated agent
decision here. Nothing in this module builds one from a model's output.

Every journal is checked with `assert_balanced` before it is stored, so an
unbalanced proposal is refused at write time and never reaches a reviewer.
"""

from __future__ import annotations

import json

from fastapi import HTTPException

from . import db
from .accounting.money import InvariantError, JournalLine, assert_balanced, cash_delta, money

REVIEWER = "local-reviewer"


def _fail(code, message, status=422):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


def _lines(journal):
    return [JournalLine(account=row["account"], fund=row["fund"],
                        debit_cents=row["debit_cents"], credit_cents=row["credit_cents"])
            for row in journal]


def _row(row):
    return {
        "id": row["id"], "agent": row["agent"], "kind": row["kind"], "title": row["title"],
        "summary": row["summary"], "verified": bool(row["verified"]), "status": row["status"],
        "journal": json.loads(row["journal"]) if row["journal"] else None,
        "effects": json.loads(row["effects"]) if row["effects"] else None,
        "finding_id": row["finding_id"],
    }


def store(connection, ws, proposal):
    """Persist one proposal. Journals must balance before they are visible to anyone."""
    journal = proposal.get("journal")
    if journal:
        try:
            assert_balanced(_lines(journal))
        except InvariantError as exc:
            _fail("unbalanced_journal", f"A proposed journal must balance before it is stored: {exc}")
        if not proposal.get("verified"):
            # A journal moves money between funds. Only a claim that survived
            # independent review may propose one, whatever kind it calls itself,
            # which is what keeps unreviewed triage out of the ledger.
            _fail("unreviewed_journal",
                  "A journal may only be proposed from an independently reviewed claim")
    connection.execute(
        "INSERT INTO approvals(id, ws, snapshot_id, run_id, finding_id, task_id, agent, kind, title, summary,"
        " journal, effects, verified, status, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?)"
        " ON CONFLICT(id) DO NOTHING",
        (proposal["id"], ws, proposal.get("snapshot_id"), proposal.get("run_id"),
         proposal.get("finding_id"), proposal.get("task_id"), proposal["agent"], proposal["kind"],
         proposal["title"], proposal["summary"],
         db.encode(journal) if journal else None,
         db.encode(proposal["effects"]) if proposal.get("effects") else None,
         int(bool(proposal.get("verified"))), db.now()),
    )


def listing(connection, ws, snapshot_id=None):
    """Every proposal in the workspace, the ones still waiting on a person first.

    A *pending* proposal raised against a snapshot that has since been superseded
    describes evidence that has changed underneath it — the finding behind it is
    no longer in the bundle at all — so it is marked rather than left looking
    current. An *already decided* one is the permanent record of what a person
    chose at the time, and is neither rewritten nor removed.
    """
    rows = []
    for row in connection.execute(
            "SELECT * FROM approvals WHERE ws=? ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, rowid",
            (ws,)):
        approval = _row(row)
        if approval["status"] == "pending" and _superseded(row, snapshot_id):
            approval["title"] = "Superseded evidence · " + approval["title"]
            approval["summary"] = (
                "The records this was raised against have been superseded by a newer snapshot, so the "
                "finding behind it is no longer in this workspace. Rerun the investigation against the "
                "current snapshot before acting on it. "
            ) + approval["summary"]
        rows.append(approval)
    return rows


def _superseded(row, snapshot_id):
    """True when the proposal names a snapshot and it is not the one in force."""
    return bool(snapshot_id and row["snapshot_id"] and row["snapshot_id"] != snapshot_id)


# --------------------------------------------------------------------------- #
# The human decision
# --------------------------------------------------------------------------- #

def decide(ws, approval_id, decision, reviewer=REVIEWER):
    """The only path out of `pending`. Agents may never reach it."""
    if decision not in {"approved", "rejected"}:
        _fail("invalid_decision", "A decision is either approved or rejected")
    with db.connect() as connection:
        row = connection.execute("SELECT * FROM approvals WHERE ws=? AND id=?", (ws, approval_id)).fetchone()
        if not row:
            _fail("approval_not_found", "Unknown approval in this workspace", 404)
        if row["status"] != "pending":
            _fail("already_decided", f"{approval_id} was already {row['status']}", 409)
        connection.execute("UPDATE approvals SET status=?, decided_at=?, decided_by=? WHERE ws=? AND id=?",
                           (decision, db.now(), reviewer, ws, approval_id))
        db.event(connection, ws, "approval_decided", {
            "approval_id": approval_id, "decision": decision, "kind": row["kind"],
            "finding_id": row["finding_id"], "task_id": row["task_id"],
            "verified_by_auditor": bool(row["verified"]),
            "applied": False,
            "note": "Recorded as a human decision. No payment, posting or payroll change is executed.",
        }, actor=reviewer)
        _record_precedent(connection, ws, row, decision, reviewer)


def _record_precedent(connection, ws, row, decision, reviewer):
    """Turn a human decision into a precedent a later run can check.

    This is the only writer of the `precedents` table, which is deliberate: a
    precedent must never exist without a human decision behind it. The agent
    proposes, the human decides, and only the decision becomes memory — an
    agent cannot promote its own conclusion into guidance for its next run.

    What is stored is the decision and its scope, not an instruction to repeat
    it. A later run is told to re-check applicability against current evidence
    and to record why it declined a precedent that no longer fits (see
    agents/cfo.py's memory_checks). A vendor name matching is not grounds to
    reuse a precedent whose governing document has since changed.
    """
    pattern = (row["title"] or "").strip()
    if not pattern:
        return

    verb = "approved" if decision == "approved" else "rejected"
    guidance = (
        f"A human reviewer {verb} this proposal on {db.now()[:10]}. "
        f"Treat that as precedent for the same situation only. Re-check it against the "
        f"current snapshot before relying on it, and say so if the governing evidence changed."
    )
    connection.execute(
        "INSERT INTO precedents (id, ws, pattern, verdict, guidance, scope, source_finding_id,"
        " source_approval_id, decided_by, created_at, status, uses)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,'active',0)",
        (db.uid("PB"), ws, pattern, decision, guidance,
         json.dumps({"agent": row["agent"], "kind": row["kind"]}),
         row["finding_id"], row["id"], reviewer, db.now()),
    )


def active_precedents(connection, ws: str) -> list[dict]:
    """Reviewed precedent available to a run, newest first. Read by
    agents/cfo.py's context() so a run sees what the human has already
    decided, and by projection.py so the Learning tab reflects it."""
    rows = connection.execute(
        "SELECT * FROM precedents WHERE ws=? AND status='active' ORDER BY created_at DESC LIMIT 20",
        (ws,),
    ).fetchall()
    return [
        {
            "id": r["id"], "pattern": r["pattern"], "verdict": r["verdict"],
            "guidance": r["guidance"], "source_finding_id": r["source_finding_id"],
            "decided_by": r["decided_by"], "decided_at": r["created_at"], "uses": r["uses"],
        }
        for r in rows
    ]


def note_precedent_uses(connection, ws: str, precedent_ids: list[str]) -> None:
    """Count a precedent as used when a run actually checked it. Applied or
    rejected both count — a precedent correctly declined as stale did its job."""
    for precedent_id in precedent_ids:
        connection.execute(
            "UPDATE precedents SET uses = uses + 1 WHERE ws=? AND id=?", (ws, precedent_id)
        )


#: What approving or rejecting actually did, so the log never overstates it.
_OUTCOME = {
    "approved": "Approved by {actor}. The report's after-figures now treat the finding it resolves as "
                "settled. No payment, posting or payroll change was executed.",
    "rejected": "Rejected by {actor}. The proposal stays on record as refused and nothing was applied.",
}


def decisions(connection, ws):
    """The human's own decisions, as Decision records for the Reasoning log.

    Every action in a run reaches the log, and a person deciding a proposal is an
    action — the one the product exists to make legible. `decide` already writes
    the event; without this it stopped there and the log showed only the agents.
    """
    titles = {row["id"]: row for row in connection.execute(
        "SELECT id, run_id, title FROM approvals WHERE ws=?", (ws,))}
    out = []
    for row in connection.execute(
            "SELECT actor, created_at, payload FROM events WHERE ws=? AND kind='approval_decided'"
            " ORDER BY created_at, rowid", (ws,)):
        payload = json.loads(row["payload"])
        approval_id, verdict, actor = payload["approval_id"], payload["decision"], row["actor"]
        proposal = titles.get(approval_id)
        run = (proposal["run_id"] if proposal else None) or "Human decisions"
        unreviewed = "" if payload.get("verified_by_auditor") else \
            " The Internal Auditor had not reviewed this proposal."
        out.append({
            "id": f"decision-{approval_id}", "run": run, "time": row["created_at"],
            # The contract's agent vocabulary has no human in it. `actor` names who
            # really decided; `agent` only says whose run the decision belongs to, and
            # a human decision belongs to the organization rather than any one agent.
            "agent": "orchestrator", "actor": actor,
            "action": f"Human decision: {approval_id} {verdict}",
            "summary": f"A person, not an agent, {verdict} this proposal.{unreviewed} {payload['note']}",
            "tags": [],
            "when": {"run": run, "step": "Approvals", "started": row["created_at"],
                     "finished": row["created_at"],
                     "trigger": proposal["title"] if proposal else approval_id},
            # A person decided it. No tool was called, and claiming one would be a lie.
            "how": [],
            "why": "Recorded from the Approvals tab. SchoolTrace stores that the reviewer decided and "
                   "when, not the reasoning behind it, so nothing further is claimed here.",
            "alternatives": [
                {"option": verdict, "reason": f"Chosen by {actor}.", "chosen": True},
                {"option": "rejected" if verdict == "approved" else "approved",
                 "reason": "The only other option this proposal offered.", "chosen": False},
            ],
            "memory_checks": [], "outcome": _OUTCOME[verdict].format(actor=actor),
        })
    return out


# --------------------------------------------------------------------------- #
# What an approval changes
# --------------------------------------------------------------------------- #

def comparisons(approvals, findings):
    """Before and after, computed from what approval actually changes.

    Exact integer arithmetic over amounts the engine produced. An "after" exists
    only because a decision exists; with nothing decided there is nothing to
    compare, and the caller shows that rather than an empty table.
    """
    pending_or_approved = [a for a in approvals if a["status"] != "rejected"]
    if not pending_or_approved:
        return [], None

    approved = {a["id"] for a in approvals if a["status"] == "approved"}
    resolved_findings = {a["finding_id"] for a in approvals
                         if a["id"] in approved and a.get("finding_id")}

    priced = {f["id"]: f["amount_cents"] for f in findings if f["amount_cents"] is not None}
    exposure_before = sum(priced.values())
    exposure_after = sum(amount for fid, amount in priced.items() if fid not in resolved_findings)

    open_before = sum(1 for a in approvals if a["status"] == "pending") + len(approved)
    open_after = sum(1 for a in approvals if a["status"] == "pending")

    rows = [{"label": "Decisions outstanding", "before": str(open_before), "after": str(open_after)}]
    if priced:
        rows.append({"label": "Reviewed exposure", "before": money(exposure_before),
                     "after": money(exposure_after)})

    cash = 0
    for approval in approvals:
        if approval["id"] in approved and approval["journal"]:
            cash += cash_delta(_lines(approval["journal"]))
    rows.append({"label": "Cash", "before": "unchanged",
                 "after": "unchanged" if cash == 0 else money(cash)})

    gate = next((a["id"] for a in approvals if a["status"] == "pending" and a["journal"]), None)
    return rows, gate
