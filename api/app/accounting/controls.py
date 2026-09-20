"""Deterministic control tests over committed records.

Every test here is arithmetic or set logic that a person can re-derive by hand. D2 reads
what this produces and judges only what the rules cannot settle; it never recomputes any
of it and it never produces a number.

## A passing test is still a finding

"No exact-key duplicate in the supplied register" is a statement about what was tested,
and it belongs on screen beside what was *not*. A report that only ever shows problems
teaches a reader that silence means safety, when silence usually means nobody looked.

## What these are not

A control exception is a question, not a verdict. An invoice appearing twice is a
duplicate *candidate* — the same obligation can legitimately reach two source systems,
and nothing here tests whether either copy was paid. A round-number payment is a round
number. Wording that implies otherwise would be the most damaging kind of bug in this
file, because it is the kind a reader believes.

## Ids name the finding, not its members

A reviewer attaches follow-up to `(finding_id, snapshot_id)`. An id derived from the rows
currently in a group moves when the group gains one, which orphans that note and
re-presents the finding as new. Ids here are hashed from the *claim* — this vendor, this
number, this amount — so they are stable however many records share them.
"""

from __future__ import annotations

import re
from collections import defaultdict
from hashlib import sha256

from .match import find_duplicates

#: Payments at or above this are tested for suspicious roundness. Below it, round
#: numbers are ordinary: a 50.00 subscription is not a finding.
ROUND_FLOOR_CENTS = 100_000
#: A payment is "round" when it is an exact multiple of this.
ROUND_TO_CENTS = 100_000


def _digest(*parts: str) -> str:
    return sha256("|".join(parts).encode()).hexdigest()[:12]


def _by_role(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["role"]].append(record)
    return grouped


def _normalize_name(value: str) -> str:
    """Company names, reduced to what distinguishes them.

    Legal suffixes and punctuation are dropped because "Acme Ltd." and "Acme Limited"
    are one counterparty. Nothing stronger than that: aggressive normalization merges
    companies that are genuinely different, and a false duplicate-vendor finding sends
    someone to delete a real supplier.
    """
    text = value.strip().casefold()
    text = re.sub(r"[.,'\"()]", "", text)
    text = re.sub(r"\b(inc|llc|ltd|limited|corp|corporation|co|plc|gmbh|sa|bv)\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _finding(key, title, role, status, explanation, *, rows=(), amount=None,
             action="Review the original records with the finance team."):
    evidence = sorted({(r["source_id"], r["locator"]) for r in rows})
    return {
        "id": key, "title": title, "role": role, "status": status,
        "explanation": explanation, "amount_cents": amount, "action": action,
        "origin": "deterministic",
        "review": "Rules-based control test. Not an agent's verdict and not an audit opinion.",
        "evidence": [{"source_id": s, "line": n} for s, n in evidence],
        "record_keys": sorted({r["record_key"] for r in rows}),
    }


# --------------------------------------------------------------------------- #
# The tests
# --------------------------------------------------------------------------- #

def duplicate_invoices(grouped, config) -> list[dict]:
    records = [r for rows in grouped.values() for r in rows]
    found = []
    candidates = find_duplicates(records)
    for candidate in candidates:
        rows = [r for r in grouped["vendor_invoices"]
                if r["record_key"] in candidate["record_keys"]]
        found.append(_finding(
            "ctl-duplicate-invoice-" + candidate["id"].split("-")[-1],
            "Possible duplicate invoice", "ap", "attention",
            "The same vendor, invoice number, amount and currency appear on more than "
            "one record. This does not establish that anything was paid twice; the same "
            "obligation reaching two source systems looks identical.",
            rows=rows, amount=candidate["exposure_cents"],
            action="Compare the originals and the payment status of each before "
                   "proposing a correction."))
    if not candidates and grouped["vendor_invoices"]:
        found.append(_finding(
            "ctl-duplicate-invoice", "Exact-key duplicate invoice test", "ap", "pass",
            "No repeated vendor, invoice number, amount and currency in the supplied "
            "register. Near-duplicates under altered numbers, and whether anything was "
            "paid twice, were not tested.",
            rows=grouped["vendor_invoices"]))
    return found


def duplicate_vendors(grouped, config) -> list[dict]:
    by_name: dict[str, list[dict]] = defaultdict(list)
    for record in grouped["vendors"]:
        name = _normalize_name(record["payload"].get("name", ""))
        if name:
            by_name[name].append(record)

    found = []
    for name, rows in sorted(by_name.items()):
        if len(rows) < 2:
            continue
        found.append(_finding(
            "ctl-duplicate-vendor-" + _digest(name),
            "Vendor recorded more than once", "ap", "attention",
            "Two or more vendor records reduce to the same name once legal suffixes and "
            "punctuation are set aside. One counterparty under two ids splits its "
            "spend and can let the same bill be paid on each.",
            rows=rows,
            action="Confirm whether these are one counterparty before merging; two "
                   "genuinely different entities can have near-identical names."))
    if not found and grouped["vendors"]:
        found.append(_finding(
            "ctl-duplicate-vendor", "Duplicate vendor test", "ap", "pass",
            "No two vendor records reduce to the same name. Bank-detail overlap and "
            "shared addresses were not tested.", rows=grouped["vendors"]))
    return found


def self_approval(grouped, config) -> list[dict]:
    """Whoever raised the order must not be whoever approved paying it."""
    approvals_by_target: dict[str, list[dict]] = defaultdict(list)
    for record in grouped["approvals"]:
        target = record["payload"].get("target_id", "")
        if target:
            approvals_by_target[target].append(record)

    orders = {r["payload"].get("po_id"): r for r in grouped["purchase_orders"]}
    found, tested = [], 0
    for invoice in grouped["vendor_invoices"]:
        payload = invoice["payload"]
        order = orders.get(payload.get("po_id"))
        approvals = approvals_by_target.get(payload.get("record_id"), []) \
            or approvals_by_target.get(invoice["record_key"], [])
        if not order or not approvals:
            continue
        tested += 1
        requester = (order["payload"].get("approver") or "").strip().casefold()
        approvers = {(a["payload"].get("actor") or "").strip().casefold() for a in approvals}
        # A documented delegation is the legitimate case this must not flag.
        delegated = any((a["payload"].get("delegation") or "").strip() for a in approvals)
        if requester and requester in approvers and not delegated:
            found.append(_finding(
                "ctl-self-approval-" + _digest(invoice["record_key"]),
                "Order raised and invoice approved by one person", "ap", "attention",
                "The person who raised the purchase order also approved paying the "
                "invoice. The segregation-of-duties control does not permit that unless "
                "a delegation is recorded, and none is.",
                rows=[invoice, order, *approvals],
                action="Have an independent approver review the invoice, or record the "
                       "delegation that authorized this."))
    if not found and tested:
        found.append(_finding(
            "ctl-self-approval", "Segregation of duties on invoice approval", "ap", "pass",
            f"In {tested} invoice(s) with both an order and an approval, the requester "
            "and the approver differ, or a delegation is recorded. Invoices missing "
            "either record could not be tested.",
            rows=grouped["vendor_invoices"]))
    return found


def post_close_entries(grouped, config) -> list[dict]:
    """Journal entries written after their period was locked.

    The distinction that matters is between the date an entry *carries* and the date it
    was *written*. An entry dated 28 September is unremarkable; one dated 28 September
    and written on 12 October, after September closed, moved a number in a period
    somebody had already signed off. Only a posting timestamp separates the two, so
    where the records do not carry one this reports a gap rather than guessing.
    """
    locks = {}
    for record in grouped["period_locks"]:
        payload = record["payload"]
        period, locked_at = payload.get("period", ""), payload.get("locked_at", "")
        if period and locked_at:
            locks[period] = record

    if not locks:
        return [_finding(
            "ctl-post-close", "Post-close entry test", "py", "gap",
            "No period locks were supplied, so an entry written after a period closed "
            "cannot be distinguished from one written before it.",
            action="Upload the period-lock register to enable this test.")]

    timestamped = [e for e in grouped["ledger"] if e["payload"].get("posted_at")]
    if not timestamped:
        return [_finding(
            "ctl-post-close", "Post-close entry test", "py", "gap",
            "The ledger carries no posting timestamp, so when each entry was written "
            "cannot be established. An entry dated inside a closed period is ordinary; "
            "one written after the lock is not, and these records cannot tell them apart.",
            rows=grouped["ledger"],
            action="Supply the ledger with a posted_at column from the source system.")]

    # Grouped by journal, not by line: a journal is one act, and reporting each of its
    # lines separately would count one late entry as several exceptions.
    late: dict[str, list[dict]] = defaultdict(list)
    for entry in timestamped:
        payload = entry["payload"]
        lock = locks.get((payload.get("date") or "")[:7])
        if lock and payload["posted_at"] > lock["payload"]["locked_at"]:
            late[payload.get("entry_id", "")].append((entry, lock))

    found = []
    for entry_id, pairs in sorted(late.items()):
        lines = [entry for entry, _ in pairs]
        lock = pairs[0][1]
        found.append(_finding(
            "ctl-post-close-" + _digest(entry_id),
            "Entry written after its period was locked", "py", "attention",
            "The entry is dated inside a period the lock register shows as closed, and "
            "its posting timestamp falls after the lock. A reopening may have been "
            "authorized; nothing supplied says so.",
            rows=[*lines, lock],
            action="Find the authority for the reopening, and confirm which reported "
                   "figures moved because of it."))
    if not found:
        untested = len(grouped["ledger"]) - len(timestamped)
        note = f" {untested} entry/entries carry no timestamp and were not tested." if untested else ""
        found.append(_finding(
            "ctl-post-close", "Post-close entry test", "py", "pass",
            f"No entry was written after the lock on its period.{note}",
            rows=timestamped))
    return found


def round_number_payments(grouped, config) -> list[dict]:
    """Large payments for an exactly round amount.

    Weak on its own and deliberately worded that way: a round contract value is
    ordinary, and this only earns attention next to something else.
    """
    suspicious = [r for r in grouped["payments"]
                  if (amount := r["payload"].get("amount_cents", 0)) >= ROUND_FLOOR_CENTS
                  and amount % ROUND_TO_CENTS == 0]
    if not suspicious:
        return [_finding(
            "ctl-round-payment", "Round-amount payment test", "ap", "pass",
            "No payment at or above the tested floor is an exact round amount.",
            rows=grouped["payments"])] if grouped["payments"] else []
    return [_finding(
        "ctl-round-payment-" + _digest(r["record_key"]),
        "Payment for an exactly round amount", "ap", "attention",
        "The payment is an exact round amount at a size where that is unusual. This is "
        "a weak indicator on its own — a round contract value is ordinary — and means "
        "little unless something else about the payment is also unexplained.",
        rows=[r], amount=r["payload"].get("amount_cents"),
        action="Check the invoice behind it. Treat this as a prompt to look, not a finding.")
        for r in suspicious]


def missing_approval(grouped, config) -> list[dict]:
    """Invoices at or above the approval limit with nothing approving them."""
    limit = (config.get("settings") or {}).get("approval_limit_cents")
    if limit is None:
        return [_finding(
            "ctl-approval-limit", "Approval limit test", "ap", "gap",
            "No payment approval limit is set for this workspace, so whether an invoice "
            "needed an approval could not be tested.",
            action="Set the payment approval limit on Books.")]

    approved = {r["payload"].get("target_id") for r in grouped["approvals"]}
    exposed = [r for r in grouped["vendor_invoices"]
               if r["payload"].get("amount_cents", 0) >= int(limit)
               and r["payload"].get("record_id") not in approved
               and r["record_key"] not in approved]
    if not exposed:
        return [_finding(
            "ctl-approval-limit", "Approval limit test", "ap", "pass",
            "Every invoice at or above the approval limit carries a recorded approval.",
            rows=grouped["vendor_invoices"])]
    return [_finding(
        "ctl-missing-approval-" + _digest(r["record_key"]),
        "Invoice above the approval limit with no approval recorded", "ap", "attention",
        "The invoice is at or above this workspace's approval limit and no approval "
        "names it. The approval may exist outside the records supplied.",
        rows=[r], amount=r["payload"].get("amount_cents"),
        action="Obtain the approval, or route the invoice to an authorized approver.")
        for r in exposed]


#: Every test, in the order a reader should meet them.
TESTS = (duplicate_invoices, duplicate_vendors, self_approval,
         post_close_entries, round_number_payments, missing_approval)


def checks(records: list[dict], config: dict) -> list[dict]:
    """Every deterministic control finding for one snapshot.

    Returns dicts shaped: id, title, role, status (pass | attention | gap), explanation,
    amount_cents, action, origin, review, evidence, record_keys.
    """
    grouped = _by_role(records)
    out: list[dict] = []
    for test in TESTS:
        out.extend(test(grouped, config))
    return out


def exceptions_only(records: list[dict], config: dict) -> list[dict]:
    """The subset that needs someone to look. Passes are still reported by `checks`."""
    return [c for c in checks(records, config) if c["status"] == "attention"]
