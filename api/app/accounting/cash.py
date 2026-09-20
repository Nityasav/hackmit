"""Cash position and near-term projection, in exact integer cents.

Where reconciliation asks "does the bank agree with the books", this asks "how much is
there, and what is about to happen to it". Both are arithmetic; neither is a forecast in
the FP&A sense. A4 reads this and recommends timing; the numbers are not its to invent.

The projection is **commitments already recorded**, not a model of the future: invoices
that exist and are not yet settled, on the dates they fall due. Nothing here estimates
revenue that has not been billed or spend that has not been committed — that is C2's
job, and conflating the two would let a forecast masquerade as a bank balance.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

#: Accounts whose balance is cash. A workspace naming its bank account differently
#: supplies a chart that says so through `report_mapping`.
CASH_MAPPING = "cash"


def _by_role(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["role"]].append(record)
    return grouped


def _cash_accounts(grouped: dict[str, list[dict]]) -> set[str]:
    return {r["payload"]["account"] for r in grouped["chart"]
            if r["payload"].get("report_mapping") == CASH_MAPPING}


def _cite(record: dict, note: str) -> dict:
    return {"role": record["role"], "record_key": record["record_key"],
            "source_id": record["source_id"], "line": record["locator"], "note": note}


def position(records: list[dict], config: dict | None = None) -> dict:
    """Cash at the start of the period, what moved, and where that leaves it.

    The closing figure is derived two ways — from the ledger's cash accounts and from
    the bank lines — and both are reported. When they disagree, that disagreement *is*
    the finding, and presenting a single reconciled number would bury it.
    """
    grouped = _by_role(records)
    cash_accounts = _cash_accounts(grouped)

    opening = sum(r["payload"].get("debit_cents", 0) - r["payload"].get("credit_cents", 0)
                  for r in grouped["opening"] if r["payload"].get("account") in cash_accounts)

    ledger_movement = sum(
        r["payload"].get("debit_cents", 0) - r["payload"].get("credit_cents", 0)
        for r in grouped["ledger"] if r["payload"].get("account") in cash_accounts)

    bank_in = sum(r["payload"].get("amount_cents", 0) for r in grouped["bank_transactions"]
                  if r["payload"].get("direction") == "in")
    bank_out = sum(r["payload"].get("amount_cents", 0) for r in grouped["bank_transactions"]
                   if r["payload"].get("direction") == "out")
    bank_movement = bank_in - bank_out

    return {
        "opening_cents": opening,
        "ledger_movement_cents": ledger_movement,
        "bank_movement_cents": bank_movement,
        "closing_per_ledger_cents": opening + ledger_movement,
        "closing_per_bank_cents": opening + bank_movement,
        # Reported, never silently reconciled. A4 escalates this rather than picking one.
        "difference_cents": ledger_movement - bank_movement,
        "agrees": ledger_movement == bank_movement,
        "cash_accounts": sorted(cash_accounts),
        "inflow_cents": bank_in,
        "outflow_cents": bank_out,
        "note": "Closing cash is derived from the ledger and from the bank separately. "
                "A difference between them is unreconciled and is not resolved here.",
    }


def _settled(grouped: dict[str, list[dict]], role: str, key_field: str) -> set[str]:
    """Which obligations already have cash recorded against them."""
    settled: set[str] = set()
    for record in grouped[role]:
        reference = (record["payload"].get(key_field) or "").strip()
        if reference:
            settled.add(reference)
    return settled


def project(records: list[dict], config: dict | None = None, horizon_days: int = 45) -> dict:
    """What is committed to move, and when, from records that already exist.

    Only unsettled obligations count: an invoice with a payment recorded against it has
    already happened and belongs in `position`, not in what is still to come.
    """
    grouped = _by_role(records)
    config = config or {}
    start = config.get("end") or date.today().isoformat()
    horizon = (date.fromisoformat(start) + timedelta(days=horizon_days)).isoformat()

    paid = _settled(grouped, "payments", "invoice_number")
    received = _settled(grouped, "remittances", "invoice_refs")

    outflows, inflows = [], []
    for record in grouped["vendor_invoices"]:
        payload = record["payload"]
        if payload.get("invoice_number", "") in paid:
            continue
        outflows.append({
            "record_key": record["record_key"], "due_date": payload.get("due_date", ""),
            "amount_cents": payload.get("amount_cents", 0),
            "counterparty": payload.get("vendor_id", ""),
            "citations": [_cite(record, "unsettled bill")],
        })
    for record in grouped["customer_invoices"]:
        payload = record["payload"]
        if payload.get("invoice_number", "") in received:
            continue
        inflows.append({
            "record_key": record["record_key"], "due_date": payload.get("due_date", ""),
            "amount_cents": payload.get("amount_cents", 0),
            "counterparty": payload.get("customer_id", ""),
            "citations": [_cite(record, "uncollected invoice")],
        })

    current = position(records, config)
    opening = current["closing_per_bank_cents"]

    # Walk the commitments in date order. Outflows are near-certain; inflows depend on a
    # customer paying on time, so the two are reported separately rather than summed
    # into one optimistic line.
    committed_out = sum(o["amount_cents"] for o in outflows if o["due_date"] <= horizon)
    expected_in = sum(i["amount_cents"] for i in inflows if i["due_date"] <= horizon)

    shortfall_date = ""
    running = opening
    for item in sorted(outflows, key=lambda o: o["due_date"]):
        if item["due_date"] > horizon:
            break
        running -= item["amount_cents"]
        if running < 0 and not shortfall_date:
            shortfall_date = item["due_date"]

    return {
        "as_at": start,
        "horizon": horizon,
        "opening_cents": opening,
        "committed_outflows_cents": committed_out,
        "expected_inflows_cents": expected_in,
        # The number that matters: what is left if nobody pays us on time.
        "position_before_collections_cents": opening - committed_out,
        "position_with_collections_cents": opening - committed_out + expected_in,
        "first_shortfall_date": shortfall_date,
        "outflows": sorted(outflows, key=lambda o: o["due_date"])[:50],
        "inflows": sorted(inflows, key=lambda i: i["due_date"])[:50],
        "counts": {"unsettled_bills": len(outflows), "uncollected_invoices": len(inflows)},
        "note": "Commitments already recorded, on their recorded dates. Nothing here "
                "estimates unbilled revenue or uncommitted spend. Expected collections "
                "are shown separately because they depend on a customer paying on time.",
    }
