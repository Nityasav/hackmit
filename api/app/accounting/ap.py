"""Deterministic accounts-payable calculations. Integer cents, no model involvement.

Same contract as `payroll.py`: every amount here is a pure function of committed
structured records, so the Internal Auditor can reperform it through this code
and reach an identical result. Without this module the AP agent could describe a
problem but never price one, and the auditor rejects a substantiated claim that
carries no calculation — which is why AP runs returned nothing to approve.

Scope boundary worth stating plainly: intake has no purchase-order or goods-receipt
*role*, only `po_id` and `receipt_id` references carried on an invoice. So this
module can test whether support is referenced, never whether the referenced
document agrees on amount. A three-way-match variance needs those records to exist
as records; until they do, claiming one would be inventing it.
"""

from __future__ import annotations

from .payroll import PayrollCalculation as Calculation


def _invoices(records: list[dict]) -> list[dict]:
    return [r for r in records if r["role"] == "invoice"]


def _sources(rows: list[dict]) -> tuple[str, ...]:
    return tuple(sorted({r["source_id"] for r in rows}))


def _total(rows: list[dict]) -> int:
    return sum(r["payload"]["amount_cents"] for r in rows)


def invoiced_total(invoices: list[dict]) -> Calculation:
    """Total invoiced across the committed invoice records."""
    return Calculation(
        id="ap-invoiced-total",
        description="Total invoiced across the committed invoice records.",
        source_ids=_sources(invoices),
        amount_cents=_total(invoices),
        cash_delta_cents=0,
        category="none",
        basis=f"{len(invoices)} invoice record(s) in this snapshot.",
    )


def duplicate_exposure(invoices: list[dict]) -> Calculation:
    """Amount at risk from invoices repeating a vendor's invoice number.

    The first occurrence in each group is treated as the original, so the
    exposure is what a second payment would cost. A repeated number is an
    indicator, not proof that anything was paid twice.
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for record in invoices:
        payload = record["payload"]
        key = (payload.get("vendor_id", ""), payload.get("invoice_number", ""))
        groups.setdefault(key, []).append(record)
    repeated = {key: rows for key, rows in groups.items() if len(rows) > 1}
    exposure = sum(_total(sorted(rows, key=lambda r: r["payload"]["record_id"])[1:])
                   for rows in repeated.values())
    return Calculation(
        id="ap-duplicate-exposure",
        description="Invoice amount repeating a vendor's invoice number, beyond the first occurrence.",
        source_ids=_sources(invoices),
        amount_cents=exposure,
        cash_delta_cents=0,
        category="exposure" if exposure else "none",
        basis=(f"{len(repeated)} vendor/invoice-number group(s) occur more than once."
               if repeated else f"No invoice number repeats for a vendor across {len(invoices)} invoice(s)."),
    )


def _unreferenced(invoices: list[dict], field: str) -> list[dict]:
    return [r for r in invoices if not r["payload"].get(field)]


def without_purchase_order(invoices: list[dict]) -> Calculation:
    """Invoiced amount carrying no purchase-order reference."""
    unmatched = _unreferenced(invoices, "po_id")
    amount = _total(unmatched)
    return Calculation(
        id="ap-without-purchase-order",
        description="Invoiced amount with no purchase-order reference recorded on the invoice.",
        source_ids=_sources(invoices),
        amount_cents=amount,
        cash_delta_cents=0,
        category="exposure" if amount else "none",
        basis=(f"{len(unmatched)} of {len(invoices)} invoice(s) reference no purchase order. "
               "Absence of a reference is not proof the purchase was unauthorized."
               if unmatched else f"All {len(invoices)} invoice(s) reference a purchase order."),
    )


def without_goods_receipt(invoices: list[dict]) -> Calculation:
    """Invoiced amount carrying no goods-receipt reference."""
    unmatched = _unreferenced(invoices, "receipt_id")
    amount = _total(unmatched)
    return Calculation(
        id="ap-without-goods-receipt",
        description="Invoiced amount with no goods-receipt reference recorded on the invoice.",
        source_ids=_sources(invoices),
        amount_cents=amount,
        cash_delta_cents=0,
        category="exposure" if amount else "none",
        basis=(f"{len(unmatched)} of {len(invoices)} invoice(s) reference no goods receipt. "
               "Receipt of goods may be recorded elsewhere; this tests the invoice record only."
               if unmatched else f"All {len(invoices)} invoice(s) reference a goods receipt."),
    )


def calculations(records: list[dict]) -> list[Calculation]:
    """Every AP calculation this snapshot supports, in a stable order.

    An empty list means no invoice records are committed, so no AP amount may be
    asserted at all.
    """
    invoices = _invoices(records)
    if not invoices:
        return []
    results = [invoiced_total(invoices), duplicate_exposure(invoices),
               without_purchase_order(invoices), without_goods_receipt(invoices)]
    return sorted(results, key=lambda c: c.id)
