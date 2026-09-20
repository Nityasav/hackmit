"""Pydantic models for AP source records: vendors, POs, receipts, invoices, approvals.

These mirror `app/agents/data/ap_sandbox.json` (contracts/README.md's fixture-owner
rule applies here too: change the model and the fixture together). Money is always
integer cents (spec.md's `Invoice / InvoiceLine` and `PurchaseOrder / Receipt` rows).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

InvoiceStatus = Literal["open", "matched", "exception", "held", "paid"]
ApprovalRecordType = Literal["invoice", "purchase_order", "payment_batch"]
BatchStatus = Literal["pending", "released"]


class Vendor(BaseModel):
    id: str
    name: str
    status: Literal["active", "hold"]
    bank_account_last4: str
    bank_changed_at: str | None = None


class PurchaseOrder(BaseModel):
    id: str
    line: int
    vendor_id: str
    description: str
    ordered_qty: float
    ordered_amount_cents: int
    approved_by: str
    approval_date: str


class GoodsReceipt(BaseModel):
    id: str
    po_id: str
    po_line: int
    received_date: str
    received_qty: float
    batch: str
    acceptance_ref: str


class Invoice(BaseModel):
    id: str
    vendor_id: str
    po_id: str | None
    po_line: int | None
    receipt_ids: list[str]
    invoice_date: str
    due_date: str
    service_start: str | None = None
    service_end: str | None = None
    gross_cents: int
    tax_cents: int
    net_cents: int
    credit_memo_ids: list[str]
    status: InvoiceStatus


class Approval(BaseModel):
    id: str
    record_type: ApprovalRecordType
    record_id: str
    actor: str
    authority: str
    action: Literal["approved", "rejected"]
    decided_at: str


class PaymentBatch(BaseModel):
    id: str
    invoice_ids: list[str]
    held_invoice_ids: list[str]
    hold_reasons: dict[str, str]
    total_cents: int
    status: BatchStatus
    note: str | None = None
