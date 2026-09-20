"""Costs the period incurred that nobody has billed yet.

A goods receipt says something was delivered. An invoice says someone asked to be paid
for it. Between the two sits a cost the period owes and has no bill for, and leaving it
out understates what the month actually cost.

**A proposal, never a posting.** Every journal here is built, balanced and handed to a
person. Nothing in this module or downstream of it writes to the ledger, and the amount
comes from a receipt that exists rather than from an estimate.

## What is deliberately not here

Estimating an accrual with no receipt behind it — "cloud usage is usually about this" —
is a judgment, not a derivation. B2's model may propose one in prose, but it cannot get
a number from this module for it, and `approvals.store` refuses a journal from a claim
nothing independently reviewed. An accrual whose basis is a guess would look exactly like
one whose basis is a delivery note, and that is the distinction worth keeping.
"""

from __future__ import annotations

from collections import defaultdict

from .money import JournalLine, assert_balanced

#: Where an unbilled receipt is credited until the invoice arrives.
ACCRUED_LIABILITY_MAPPING = "accruals"


def _by_role(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["role"]].append(record)
    return grouped


def _accrual_account(grouped) -> str | None:
    for record in grouped["chart"]:
        if record["payload"].get("report_mapping") == ACCRUED_LIABILITY_MAPPING:
            return record["payload"]["account"]
    return None


def _expense_account(grouped, order) -> str | None:
    """The account the eventual invoice would hit, taken from the order's own description.

    Matched against the chart rather than assumed: if the order does not name something
    the chart recognizes, the accrual is reported as unaccountable instead of being
    posted to a default that would quietly misstate the category.
    """
    described = (order["payload"].get("description") or "").strip().casefold()
    if not described:
        return None
    for record in grouped["chart"]:
        payload = record["payload"]
        if payload.get("type") != "expense":
            continue
        if (payload.get("name") or "").strip().casefold() == described:
            return payload["account"]
    return None


def unbilled_receipts(records: list[dict], config: dict | None = None) -> dict:
    """Deliveries inside the period with no invoice against them.

    The amount is the receipt's own, which is what was actually delivered. Using the
    order's amount instead would accrue what was promised rather than what arrived.
    """
    config = config or {}
    grouped = _by_role(records)
    start, end = config.get("start", ""), config.get("end", "")

    billed_orders = {r["payload"].get("po_id") for r in grouped["vendor_invoices"]
                     if r["payload"].get("po_id")}
    orders = {r["payload"].get("po_id"): r for r in grouped["purchase_orders"]}
    accrual_account = _accrual_account(grouped)

    proposals, unaccountable = [], []
    for receipt in grouped["goods_receipts"]:
        payload = receipt["payload"]
        received = payload.get("received_date", "")
        po_id = payload.get("po_id", "")
        if po_id in billed_orders:
            continue
        if start and end and not (start <= received <= end):
            continue
        order = orders.get(po_id)
        amount = payload.get("amount_cents", 0)
        if not order or not amount:
            unaccountable.append({
                "receipt_key": receipt["record_key"], "po_id": po_id,
                "reason": "No purchase order in the committed population names this receipt."})
            continue
        expense_account = _expense_account(grouped, order)
        if not expense_account or not accrual_account:
            unaccountable.append({
                "receipt_key": receipt["record_key"], "po_id": po_id,
                "amount_cents": amount,
                "reason": "The chart does not name an account for what this order "
                          "describes, so the cost cannot be categorized. Posting it to a "
                          "default would misstate the category quietly."})
            continue

        journal = [
            JournalLine(account=expense_account, fund="", debit_cents=amount),
            JournalLine(account=accrual_account, fund="", credit_cents=amount),
        ]
        # Balanced before it can be proposed, not after a reviewer has looked at it.
        assert_balanced(journal)
        proposals.append({
            "id": "accrual-" + receipt["record_key"].replace("\x1f", "-"),
            "receipt_key": receipt["record_key"],
            "po_id": po_id,
            "vendor_id": order["payload"].get("vendor_id", ""),
            "received_date": received,
            "amount_cents": amount,
            "journal": [{"account": line.account, "debit_cents": line.debit_cents,
                         "credit_cents": line.credit_cents} for line in journal],
            "basis": "A goods receipt inside the period with no invoice against its "
                     "order. The amount is the receipt's own, so it is what arrived "
                     "rather than what was ordered.",
            "evidence": [
                {"role": "goods_receipts", "record_key": receipt["record_key"],
                 "source_id": receipt["source_id"], "line": receipt["locator"]},
                {"role": "purchase_orders", "record_key": order["record_key"],
                 "source_id": order["source_id"], "line": order["locator"]},
            ],
        })

    return {
        "proposals": sorted(proposals, key=lambda p: -p["amount_cents"]),
        "unaccountable": unaccountable,
        "total_cents": sum(p["amount_cents"] for p in proposals),
        "accrual_account": accrual_account,
        "note": "Proposals only. Nothing here posts, and every amount comes from a "
                "delivery that was recorded rather than from an estimate. A cost with no "
                "receipt behind it is not proposed at all.",
    }
