"""What a person decided last period, and whether it still applies to this one.

The gate for this phase is one sentence: **a correction changes the next period's
behaviour, with a recorded check.** Both halves matter, and the second is the harder one.

## Only a human decision becomes memory

`approvals._record_precedent` is the sole writer of the `precedents` table, and it runs
only when a person decides a proposal. An agent cannot promote its own conclusion into
guidance for its next run. That constraint is what makes this memory worth having: every
row in it is something a person actually said.

## A precedent is never applied. It is checked, and the check is recorded.

Carrying a decision forward unexamined is how a one-off exception becomes a policy nobody
chose. So `check()` re-tests each precedent against the *current* period's records and
writes the outcome to `precedent_checks` — including when it declines one. A precedent
correctly declined as stale did its job, and the record of the declining is the evidence
that it was considered rather than ignored.

The check is deliberately narrow and deterministic. A precedent applies to this period
when the condition it was decided about is present here too, and the governing evidence
behind it has not changed. Anything else — a similar vendor, a comparable amount, the
general shape of the thing — is a judgment, and a judgment about whether last month's
decision covers this month's facts is exactly what a person is for.

## Lineage

A workspace is one period. `continues` names the workspace before it, so September's
decisions can reach October without reaching a different company that happens to share a
finding title. The chain is walked rather than stored flat, so inserting a period between
two others cannot leave a stale copy behind.
"""

from __future__ import annotations

import json

from . import db

#: How far back a precedent is looked for. Beyond this, a decision is history rather than
#: memory: a reviewer should be shown it, not have an agent act on it.
MAX_PERIODS_BACK = 12


def lineage(connection, ws: str) -> list[str]:
    """This workspace and the periods it continues, newest first.

    Walked through `continues` rather than read from a stored list, so a chain cannot
    disagree with itself after a period is inserted or renamed.
    """
    chain, seen, current = [], set(), ws
    while current and current not in seen and len(chain) <= MAX_PERIODS_BACK:
        row = connection.execute("SELECT config FROM workspaces WHERE id=?",
                                 (current,)).fetchone()
        if row is None:
            break
        chain.append(current)
        seen.add(current)
        current = (json.loads(row["config"]) or {}).get("continues") or ""
    return chain


def _period_of(connection, ws: str) -> str:
    row = connection.execute("SELECT config FROM workspaces WHERE id=?", (ws,)).fetchone()
    config = json.loads(row["config"]) if row else {}
    return str(config.get("start", ""))[:7]


def inherited(connection, ws: str) -> list[dict]:
    """Precedent available to this period, its own first and earlier periods after.

    Earlier periods are marked as such. A decision made about a different period is still
    a decision a person made, but whoever reads it has to be able to see that it was made
    somewhere else.
    """
    chain = lineage(connection, ws)
    if not chain:
        return []
    placeholders = ",".join("?" for _ in chain)
    rows = connection.execute(
        f"SELECT * FROM precedents WHERE ws IN ({placeholders}) AND status='active'"
        " ORDER BY created_at DESC LIMIT 50", tuple(chain)).fetchall()
    out = []
    for row in rows:
        out.append({
            "id": row["id"], "pattern": row["pattern"], "verdict": row["verdict"],
            "guidance": row["guidance"], "scope": json.loads(row["scope"] or "{}"),
            "source_finding_id": row["source_finding_id"],
            "decided_by": row["decided_by"], "decided_at": row["created_at"],
            "uses": row["uses"],
            "from_workspace": row["ws"],
            "from_period": _period_of(connection, row["ws"]),
            "own_period": row["ws"] == ws,
        })
    return out


def _governing_sources(connection, ws: str) -> dict[str, str]:
    """The documents a decision could have rested on, by name, with their content hash.

    Name to hash rather than id to hash: the same policy uploaded into the next period is
    a different source row, and comparing ids would report every document as changed.
    """
    rows = connection.execute(
        "SELECT s.name, s.sha256 FROM sources s WHERE s.ws=? AND s.committed=1", (ws,))
    return {row["name"]: row["sha256"] for row in rows}


def check(connection, ws: str, precedent: dict, findings: list[dict],
          *, actor: str = "system") -> dict:
    """Re-test one precedent against this period, and record the outcome either way.

    Returns the check, which is also written to `precedent_checks`. Declining is as much
    a result as applying: a precedent that no longer fits and was silently dropped is
    indistinguishable from one nobody looked at.
    """
    pattern = (precedent.get("pattern") or "").strip()
    still_present = [f for f in findings
                     if (f.get("title") or "").strip() == pattern
                     and f.get("status") == "attention"]

    here = _governing_sources(connection, ws)
    there = _governing_sources(connection, precedent.get("from_workspace") or ws)
    shared = set(here) & set(there)
    changed = sorted(name for name in shared if here[name] != there[name])

    if not pattern:
        applies, reason = False, "The precedent records no condition, so there is nothing to match."
    elif not still_present:
        applies, reason = False, (
            "The condition this was decided about did not arise in this period. The "
            "precedent stands unused rather than being applied to something else.")
    elif changed:
        applies, reason = False, (
            "The evidence the original decision rested on has changed since: "
            + ", ".join(changed) + ". A person has to decide again on what it says now.")
    else:
        applies, reason = True, (
            "The same condition arose again and the documents behind the original "
            "decision are unchanged, so what the reviewer decided then is on the record "
            "for it. It is context for a person, not an automatic outcome.")

    row = {
        "id": db.uid("PC"),
        "ws": ws,
        "precedent_id": precedent["id"],
        "applies": applies,
        "reason": reason,
        "matched": [f["id"] for f in still_present],
        "changed_sources": changed,
        "checked_by": actor,
        "checked_at": db.now(),
    }
    connection.execute(
        "INSERT INTO precedent_checks (id, ws, precedent_id, applies, reason, matched,"
        " changed_sources, checked_by, checked_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (row["id"], ws, row["precedent_id"], int(applies), reason,
         db.encode(row["matched"]), db.encode(changed), actor, row["checked_at"]))
    connection.execute("UPDATE precedents SET uses = uses + 1 WHERE id=?",
                       (precedent["id"],))
    return row


def apply_to_findings(connection, ws: str, findings: list[dict],
                      *, actor: str = "system") -> dict:
    """Check every inherited precedent against this period's findings.

    A finding a person has already decided keeps its exception — the control still fired,
    and hiding it would be the check quietly narrowing itself. What changes is that it
    arrives with the earlier decision attached, so the reader is answering "does last
    period's answer still hold" rather than the same question from scratch.
    """
    checks, applied = [], {}
    for precedent in inherited(connection, ws):
        result = check(connection, ws, precedent, findings, actor=actor)
        checks.append(result | {"pattern": precedent["pattern"],
                                "verdict": precedent["verdict"],
                                "from_period": precedent["from_period"],
                                "decided_by": precedent["decided_by"]})
        if result["applies"]:
            for finding_id in result["matched"]:
                applied.setdefault(finding_id, []).append(precedent)

    for finding in findings:
        matched = applied.get(finding["id"], [])
        if not matched:
            continue
        first = matched[0]
        finding["precedent"] = {
            "id": first["id"], "verdict": first["verdict"],
            "decided_by": first["decided_by"], "decided_at": first["decided_at"],
            "from_period": first["from_period"],
            "note": "A person decided this same condition in an earlier period and the "
                    "documents behind that decision are unchanged. The control still "
                    "fired; this is what was decided last time, not a reason it did not.",
        }

    return {
        "checks": checks,
        "applied": sum(1 for c in checks if c["applies"]),
        "declined": sum(1 for c in checks if not c["applies"]),
        "note": "Every precedent available to this period was re-checked against it and "
                "the outcome recorded, including the ones that were declined. Nothing "
                "here suppresses a finding.",
    }


def history(connection, ws: str, limit: int = 50) -> list[dict]:
    """Every precedent check made in this workspace, newest first."""
    rows = connection.execute(
        "SELECT * FROM precedent_checks WHERE ws=? ORDER BY rowid DESC LIMIT ?",
        (ws, limit)).fetchall()
    return [{
        "id": row["id"], "precedent_id": row["precedent_id"],
        "applies": bool(row["applies"]), "reason": row["reason"],
        "matched": json.loads(row["matched"] or "[]"),
        "changed_sources": json.loads(row["changed_sources"] or "[]"),
        "checked_by": row["checked_by"], "checked_at": row["checked_at"],
    } for row in rows]
