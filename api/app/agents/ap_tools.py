"""Retrieval tools for the AP & Payments agent.

Each function here is a typed, read-only lookup over the AP source records
(vendors, purchase orders, goods receipts, invoices, approvals, payment batches).
They answer "what do we know" questions; they never decide whether to pay anything
and never mutate state. Deciding rests with the agent's reasoning, and only a human
can release a payment batch (spec.md §8) — that path lives in app/workflows, not here.

Data is seeded from app/agents/data/ap_sandbox.json, the same fixture-per-workspace
pattern as app/store.py. Swap `_load` for a real query layer later without changing
these signatures.
"""

from __future__ import annotations

import json
from pathlib import Path

from .ap_records import Approval, GoodsReceipt, Invoice, PaymentBatch, PurchaseOrder, Vendor

DATA_DIR = Path(__file__).resolve().parent / "data"

_cache: dict[str, dict] = {}


def _load(workspace: str = "sandbox") -> dict:
    if workspace not in _cache:
        path = DATA_DIR / f"ap_{workspace}.json"
        _cache[workspace] = json.loads(path.read_text())
    return _cache[workspace]


# --- Vendors ---------------------------------------------------------------


def get_vendor(vendor_id: str, workspace: str = "sandbox") -> Vendor | None:
    """Look up one vendor by ID. Returns None if it doesn't exist."""
    for row in _load(workspace)["vendors"]:
        if row["id"] == vendor_id:
            return Vendor.model_validate(row)
    return None


def list_vendors(workspace: str = "sandbox") -> list[Vendor]:
    """All known vendors."""
    return [Vendor.model_validate(row) for row in _load(workspace)["vendors"]]


# --- Purchase orders ---------------------------------------------------------


def get_purchase_order(po_id: str, line: int | None = None, workspace: str = "sandbox") -> list[PurchaseOrder]:
    """PO lines matching `po_id` (and `line`, if given). A PO ID may span several lines."""
    rows = _load(workspace)["purchase_orders"]
    return [
        PurchaseOrder.model_validate(row)
        for row in rows
        if row["id"] == po_id and (line is None or row["line"] == line)
    ]


def list_purchase_orders(vendor_id: str | None = None, workspace: str = "sandbox") -> list[PurchaseOrder]:
    """All PO lines, optionally filtered to one vendor."""
    rows = _load(workspace)["purchase_orders"]
    return [
        PurchaseOrder.model_validate(row)
        for row in rows
        if vendor_id is None or row["vendor_id"] == vendor_id
    ]


# --- Goods receipts ----------------------------------------------------------


def get_goods_receipt(receipt_id: str, workspace: str = "sandbox") -> GoodsReceipt | None:
    """Look up one goods receipt by ID."""
    for row in _load(workspace)["goods_receipts"]:
        if row["id"] == receipt_id:
            return GoodsReceipt.model_validate(row)
    return None


def get_receipts_for_po(po_id: str, line: int | None = None, workspace: str = "sandbox") -> list[GoodsReceipt]:
    """All goods receipts recorded against a PO (and line, if given)."""
    rows = _load(workspace)["goods_receipts"]
    return [
        GoodsReceipt.model_validate(row)
        for row in rows
        if row["po_id"] == po_id and (line is None or row["po_line"] == line)
    ]


# --- Invoices ----------------------------------------------------------------


def get_invoice(invoice_id: str, workspace: str = "sandbox") -> Invoice | None:
    """Look up one invoice by ID."""
    for row in _load(workspace)["invoices"]:
        if row["id"] == invoice_id:
            return Invoice.model_validate(row)
    return None


def list_invoices(
    vendor_id: str | None = None,
    status: str | None = None,
    workspace: str = "sandbox",
) -> list[Invoice]:
    """All invoices, optionally filtered by vendor and/or status."""
    rows = _load(workspace)["invoices"]
    return [
        Invoice.model_validate(row)
        for row in rows
        if (vendor_id is None or row["vendor_id"] == vendor_id)
        and (status is None or row["status"] == status)
    ]


def find_duplicate_candidates(invoice_id: str, workspace: str = "sandbox") -> list[Invoice]:
    """Other invoices from the same vendor with the same net amount.

    This flags candidates to investigate (same vendor + same amount); it does not
    conclude they are duplicates. Separate goods receipts are common counterevidence
    — check get_receipts_for_po for each candidate before treating this as a finding.
    """
    target = get_invoice(invoice_id, workspace)
    if target is None:
        return []
    return [
        inv
        for inv in list_invoices(vendor_id=target.vendor_id, workspace=workspace)
        if inv.id != target.id and inv.net_cents == target.net_cents
    ]


# --- Approvals -----------------------------------------------------------------


def get_approvals_for_record(record_id: str, workspace: str = "sandbox") -> list[Approval]:
    """Approval records referencing a given invoice or PO ID."""
    rows = _load(workspace)["approvals"]
    return [Approval.model_validate(row) for row in rows if row["record_id"] == record_id]


# --- Payment batches ------------------------------------------------------------


def get_payment_batch(batch_id: str, workspace: str = "sandbox") -> PaymentBatch | None:
    """Look up one simulated payment batch by ID."""
    for row in _load(workspace)["payment_batches"]:
        if row["id"] == batch_id:
            return PaymentBatch.model_validate(row)
    return None


# --- Composite lookup ------------------------------------------------------------


def get_invoice_packet(invoice_id: str, workspace: str = "sandbox") -> dict | None:
    """Everything relevant to judging one invoice, gathered in one call.

    Bundles the invoice with its vendor, matched PO line, goods receipts, approvals,
    and same-vendor/same-amount duplicate candidates. This is the one-stop lookup for
    "should this invoice be paid" reasoning — it only retrieves; the agent still has
    to weigh it (three-way match tolerance, vendor bank-change risk, missing receipt,
    duplicate candidates the counterevidence clears).
    """
    invoice = get_invoice(invoice_id, workspace)
    if invoice is None:
        return None

    vendor = get_vendor(invoice.vendor_id, workspace)
    purchase_order = (
        get_purchase_order(invoice.po_id, invoice.po_line, workspace)[0]
        if invoice.po_id and get_purchase_order(invoice.po_id, invoice.po_line, workspace)
        else None
    )
    receipts = [
        r for rid in invoice.receipt_ids if (r := get_goods_receipt(rid, workspace)) is not None
    ]
    approvals = get_approvals_for_record(invoice.id, workspace)
    duplicates = find_duplicate_candidates(invoice.id, workspace)

    return {
        "invoice": invoice,
        "vendor": vendor,
        "purchase_order": purchase_order,
        "receipts": receipts,
        "approvals": approvals,
        "duplicate_candidates": duplicates,
    }
