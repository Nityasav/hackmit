"""Proposals agents make, and the decisions only a human may take.

Two rules shape this module.

**Agents propose, humans decide.** Nothing here lets an agent set a status. The
only transition out of `pending` runs through `decide`, which records who did it
and when.

**A proposal may only contain amounts the engine produced.** A specialist's
`proposed_action` is prose, and prose is not a journal. A journal is built only
from a deterministic calculation whose `category` is `reclassification`, and
only when the committed records name both funds involved. Where they do not —
which is the common case, because a destination fund is a decision, not a
derivation — the proposal is an evidence request for the structured allocation
record that `app/accounting/payroll.py` says is required, rather than a journal
against a fund nobody recorded.

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


def listing(connection, ws):
    return [_row(row) for row in connection.execute(
        "SELECT * FROM approvals WHERE ws=? ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, rowid",
        (ws,))]


# --------------------------------------------------------------------------- #
# Proposals derived from a coordinator run
# --------------------------------------------------------------------------- #

def _fund_named(records, award_id):
    """The fund name a committed record uses for an award, or None.

    Never invents one. A reclassification needs both sides named in the records;
    where the destination is not recorded, that is a question for a human, not a
    gap to fill in.
    """
    for record in records:
        payload = record["payload"]
        if payload.get("award_id") == award_id and payload.get("fund"):
            return payload["fund"]
    return None


def _unrestricted_fund(records):
    """A recorded fund not tied to any award, if the records name exactly one."""
    funds = {r["payload"]["fund"] for r in records
             if r["payload"].get("fund") and not r["payload"].get("award_id")}
    return funds.pop() if len(funds) == 1 else None


def _payroll_account(records):
    for record in records:
        if record["role"] == "chart" and record["payload"].get("report_mapping") == "payroll":
            return record["payload"].get("name") or record["payload"].get("account")
    return None


def proposals_for(run, records):
    """Every proposal a completed coordinator run supports, as plain dicts.

    Nothing is proposed from a claim's prose. A journal appears only where the
    engine produced a reclassification amount and the records name both funds.
    """
    out = []
    for accepted in run["accepted"]:
        claim = accepted["claim"]
        calculation = accepted.get("calculation")
        base = {"run_id": run["id"], "task_id": accepted["task_id"], "agent": accepted["role"],
                "snapshot_id": (run.get("scope") or {}).get("snapshot_id"),
                "finding_id": f"{run['id']}-{claim['id']}",
                # An accepted claim was reviewed; that is not the same as approved.
                "verified": True}

        if calculation and calculation["category"] == "reclassification" and calculation["amount_cents"]:
            amount = calculation["amount_cents"]
            account = _payroll_account(records)
            source_fund = _fund_named(records, _award_of(records, calculation))
            destination = _unrestricted_fund(records)
            if account and source_fund and destination:
                journal = [
                    {"account": account, "fund": destination, "debit_cents": amount, "credit_cents": 0},
                    {"account": account, "fund": source_fund, "debit_cents": 0, "credit_cents": amount},
                ]
                out.append({**base, "id": f"ADJ-{claim['id']}", "kind": "journal",
                            "title": f"Reclassify {money(amount)} out of {source_fund}",
                            "summary": f"{claim['title']}. Amount from {calculation['id']}; "
                                       f"{calculation['description']}",
                            "journal": journal,
                            "effects": [
                                {"label": source_fund, "value": f"−{money(amount)}", "tone": "good"},
                                {"label": destination, "value": f"+{money(amount)}"},
                                {"label": "Total expense", "value": "unchanged"},
                                {"label": "Cash", "value": "unchanged"
                                    if cash_delta(_lines(journal)) == 0 else money(cash_delta(_lines(journal)))},
                            ]})
                continue
            # The engine established the amount but the records do not name a
            # destination fund. Inventing one would defeat the provenance rule, so
            # ask for the record that would settle it.
            out.append({**base, "id": f"EV-{claim['id']}", "kind": "evidence",
                        "title": f"Provide a structured allocation record for {claim['title']}",
                        "summary": f"{money(amount)} is unsupported per {calculation['id']}, but the committed "
                                   "records do not name a destination fund, so no journal can be proposed "
                                   "from them. A structured allocation record would settle the split."})
            continue

        if claim["disposition"] == "substantiated":
            out.append({**base, "id": f"ACK-{claim['id']}", "kind": "decision",
                        "title": f"Decide how to resolve: {claim['title']}",
                        "summary": f"{claim['conclusion']} No deterministic calculation backs an amount, so no "
                                   "journal is proposed. Approving records your decision to act on it."})

    # Unresolved items are reported in the run's own report. They describe missing
    # evidence rather than an action to take, so they are not proposals.
    return out


def _award_of(records, calculation):
    """The award a reclassification calculation concerns, when the records name one."""
    awards = {r["payload"]["award_id"] for r in records
              if r["role"] == "payroll" and r["payload"].get("award_id")}
    return awards.pop() if len(awards) == 1 else None


def sync(ws, run, records):
    """Write any proposals this run supports that are not already recorded."""
    proposals = proposals_for(run, records)
    if not proposals:
        return
    with db.connect() as connection:
        for proposal in proposals:
            store(connection, ws, proposal)


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
