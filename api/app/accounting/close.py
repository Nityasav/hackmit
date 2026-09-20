"""Whether a period is ready to close, and what is holding it up.

A close checklist is not a progress bar. Each item is a question with an answer derived
from the records, and the period is ready only when nothing material is outstanding —
"ready" here meaning *nothing supplied contradicts it*, which is a narrower claim than it
sounds and is worded that way everywhere it appears.

B1 reads this and works the list across days. The state that matters lives in the records
rather than in the agent, so a close survives a restart, a different reviewer picking it
up, or a week between sittings.

## Blocking and non-blocking

An item that means the books are *wrong* blocks: an unbalanced trial balance, statements
that do not tie, an entry written after the lock. An item that means the books are
*incomplete in a normal way* does not: unpaid bills at month end are ordinary, and a
close that waited for them would never happen. The distinction is recorded per item
rather than inferred, so nobody has to guess which kind they are looking at.
"""

from __future__ import annotations

from collections import defaultdict

from . import controls, reconcile, statements


def _by_role(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["role"]].append(record)
    return grouped


def _item(key, title, state, detail, *, blocking=True, evidence=()):
    return {"id": key, "title": title, "state": state, "detail": detail,
            "blocking": blocking, "evidence": list(evidence)}


def checklist(records: list[dict], config: dict | None = None) -> dict:
    """Every close question, answered from the records.

    `state` is one of: `done`, `blocked`, `attention`, `not_applicable`.
    """
    config = config or {}
    grouped = _by_role(records)
    period = str(config.get("start", ""))[:7]
    items: list[dict] = []

    # --- the inputs a close cannot proceed without -------------------------
    for role, title in (("chart", "Chart of accounts"),
                        ("opening", "Opening trial balance"),
                        ("ledger", "General ledger")):
        present = bool(grouped[role])
        items.append(_item(
            f"close-input-{role}", f"{title} supplied",
            "done" if present else "blocked",
            f"{len(grouped[role])} record(s)." if present else
            "Nothing supplied. Nothing downstream of this can be checked."))

    if not grouped["ledger"]:
        return {"period": period, "items": items, "ready": False,
                "blocked_by": [i["id"] for i in items if i["state"] == "blocked"],
                "note": "No ledger was supplied, so nothing further could be assessed."}

    # --- the books agree with themselves -----------------------------------
    figures = statements.statements(records)
    trial = figures["trial_balance"]
    items.append(_item(
        "close-trial-balance", "Trial balance balances",
        "done" if trial["balances"] else "blocked",
        "Debits equal credits across every account." if trial["balances"] else
        f"Out by {trial['difference_cents']} cent(s). Every figure below inherits it."))

    sheet = figures["balance_sheet"]
    items.append(_item(
        "close-balance-sheet", "Assets equal liabilities plus equity",
        "done" if sheet["balances"] else "blocked",
        "The balance sheet balances, including the period result." if sheet["balances"]
        else f"Out by {sheet['difference_cents']} cent(s)."))

    cash = figures["cash_flow"]
    items.append(_item(
        "close-cash-flow", "Cash flow agrees with the balance sheet",
        "done" if cash["ties"] else "blocked",
        "Cash walked from the entries lands on the balance sheet figure."
        if cash["ties"] else
        f"Out by {cash['difference_cents']} cent(s); an entry was missed."))

    # --- the books agree with the outside world ----------------------------
    if grouped["bank_transactions"]:
        bank = reconcile.reconcile_bank(records, config)["totals"]
        outstanding = bank["unmatched_bank"] + bank["unmatched_book"] + bank["differing"]
        items.append(_item(
            "close-bank-reconciled", "Bank agrees with the books",
            "done" if not outstanding else "attention",
            f"{bank['matched']} of {bank['bank_lines']} bank line(s) matched."
            if not outstanding else
            f"{bank['unmatched_bank']} bank line(s) and {bank['unmatched_book']} recorded "
            f"movement(s) unmatched, {bank['differing']} differing. Each is an open "
            "question, and they are not netted against each other.",
            # Unreconciled cash does not make the ledger wrong, but closing over it means
            # signing off a cash figure nobody has agreed.
            blocking=bool(outstanding)))
    else:
        items.append(_item(
            "close-bank-reconciled", "Bank agrees with the books", "blocked",
            "No bank activity was supplied, so the cash figure is unverified."))

    # --- controls -----------------------------------------------------------
    exceptions = [c for c in controls.checks(records, config) if c["status"] == "attention"]
    post_close = [c for c in exceptions if c["id"].startswith("ctl-post-close")]
    others = [c for c in exceptions if c not in post_close]
    items.append(_item(
        "close-post-close-entries", "No entry written after the lock",
        "done" if not post_close else "blocked",
        "No entry was posted into this period after it was locked." if not post_close
        else f"{len(post_close)} entry/entries were written after the lock. A figure "
             "already signed off has moved.",
        evidence=[c["id"] for c in post_close]))
    items.append(_item(
        "close-control-exceptions", "Control exceptions reviewed",
        "done" if not others else "attention",
        "No control test raised an exception." if not others else
        f"{len(others)} exception(s) outstanding. Each is a question for a person, not "
        "a reason the ledger is wrong.",
        blocking=False, evidence=[c["id"] for c in others]))

    # --- ordinary month-end incompleteness, which does not block ------------
    unpaid = sum(1 for r in grouped["vendor_invoices"]
                 if r["payload"].get("record_id") not in {
                     p["payload"].get("invoice_number") for p in grouped["payments"]})
    items.append(_item(
        "close-open-payables", "Open payables noted",
        "done" if not unpaid else "attention",
        f"{unpaid} bill(s) unpaid at period end. Ordinary at month end; a close that "
        "waited for them would never happen.", blocking=False))

    locked = [r for r in grouped["period_locks"] if r["payload"].get("period") == period]
    items.append(_item(
        "close-lock", "Period locked",
        "done" if locked else "attention",
        "A lock is recorded for this period." if locked else
        "No lock is recorded for this period yet. Locking is what makes a later entry "
        "detectable as a post-close one.", blocking=False))

    blocked = [i["id"] for i in items if i["state"] == "blocked" and i["blocking"]]
    return {
        "period": period,
        "items": items,
        "ready": not blocked,
        "blocked_by": blocked,
        "counts": {state: sum(1 for i in items if i["state"] == state)
                   for state in ("done", "attention", "blocked")},
        "note": "Ready means nothing supplied contradicts a close. It is not an audit "
                "opinion, and it says nothing about records that were never uploaded.",
    }
