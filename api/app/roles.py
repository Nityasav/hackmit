"""The record vocabulary: what a SaaS company's books are made of.

`ingestion.py` owns the staging lifecycle; this module owns *what* may be staged.
Separating them means adding a record type is a data change, not a control-flow
change, and that the Books screen, the validators and the agent registry all read
one definition of a role instead of three that drift.

Money is always integer cents and always non-negative. Direction is carried by an
explicit column (`direction`, `debit`/`credit`) rather than a sign, so a malformed
minus cannot quietly reverse a transaction. Rates are basis points, never floats.
"""

from __future__ import annotations

from typing import Literal

Role = Literal[
    # Ledger spine
    "chart", "opening", "ledger",
    # Purchase to pay
    "vendors", "purchase_orders", "goods_receipts", "vendor_invoices", "payments",
    # Order to cash
    "customers", "customer_invoices", "remittances",
    # Cash
    "bank_transactions", "processor_payouts",
    # People and spend
    "payroll", "expenses",
    # Plan
    "budgets", "forecasts", "headcount",
    # Control
    "approvals", "period_locks", "tax_registrations",
    # Unstructured evidence
    "contract", "policy", "document", "invoice", "service", "budget",
]

#: Roles carried as text rather than tabular records.
#:
#: A document staged under a role no agent reads is preserved, hashed and
#: citable by a person, and invisible to every agent — so extracting it and
#: checking its values buys nothing. `document` is exactly that: the catch-all
#: for evidence whose kind nothing claims. The named roles beside it exist so a
#: document can keep its kind through staging and reach the agent whose charter
#: covers it, rather than all of them collapsing into the catch-all.
DOCUMENT_ROLES: frozenset[str] = frozenset({
    "contract", "policy", "document", "invoice", "service", "budget",
})

#: Required columns per structured role, in the order a person reads them.
FIELDS: dict[str, list[str]] = {
    "chart": ["account", "name", "type", "report_mapping", "effective_from"],
    "opening": ["record_id", "account", "balance_date", "debit", "credit"],
    "ledger": ["entry_id", "line_id", "date", "account", "debit", "credit"],

    "vendors": ["vendor_id", "name", "country", "payment_terms_days"],
    "purchase_orders": ["po_id", "line_id", "vendor_id", "description", "order_date", "amount", "approver"],
    "goods_receipts": ["receipt_id", "line_id", "po_id", "po_line_id", "received_date", "amount"],
    "vendor_invoices": ["record_id", "vendor_id", "invoice_number", "invoice_date", "due_date", "amount"],
    "payments": ["payment_id", "vendor_id", "payment_date", "method", "amount", "reference"],

    "customers": ["customer_id", "name", "country", "payment_terms_days"],
    "customer_invoices": ["record_id", "customer_id", "invoice_number", "invoice_date", "due_date", "amount"],
    "remittances": ["remittance_id", "customer_id", "received_date", "amount", "reference"],

    "bank_transactions": ["bank_id", "bank_account", "settlement_date", "direction", "amount", "description"],
    "processor_payouts": ["payout_id", "processor", "payout_date", "gross", "fees", "refunds", "chargebacks", "net"],

    "payroll": ["record_id", "employee_id", "period_start", "period_end", "pay_date",
                "gross", "deductions", "net", "employer_cost"],
    "expenses": ["record_id", "employee_id", "expense_date", "category", "amount", "merchant"],

    "budgets": ["record_id", "account", "period", "amount", "approval_reference"],
    "forecasts": ["record_id", "account", "period", "amount", "basis"],
    "headcount": ["record_id", "department", "period", "count"],

    "approvals": ["record_id", "actor", "authority", "action", "target_type", "target_id", "approved_at"],
    "period_locks": ["record_id", "period", "locked_at", "locked_by"],
    "tax_registrations": ["record_id", "jurisdiction", "tax_type", "rate_basis_points", "registered_from"],
}

#: Columns parsed as integer cents. The `_cents` suffix is added on the way in.
MONEY_FIELDS: frozenset[str] = frozenset({
    "debit", "credit", "amount", "gross", "deductions", "net", "employer_cost",
    "fees", "refunds", "chargebacks", "tax_amount", "unit_amount",
})

#: Columns parsed as YYYY-MM-DD.
DATE_FIELDS: frozenset[str] = frozenset({
    "date", "balance_date", "effective_from", "effective_to",
    "order_date", "received_date", "invoice_date", "due_date", "payment_date",
    "settlement_date", "payout_date", "period_start", "period_end", "pay_date",
    "expense_date", "approved_at", "locked_at", "registered_from", "registered_to",
})

#: Columns parsed as whole numbers rather than money or dates.
COUNT_FIELDS: frozenset[str] = frozenset({
    "count", "quantity", "payment_terms_days", "rate_basis_points",
})

#: Recognized on any role when present. Mapping one is how a source carries extra
#: identity — the references that let the event graph be assembled without guessing.
OPTIONAL_FIELDS: list[str] = [
    "currency", "department", "entity", "memo", "effective_to", "registered_to",
    "event_ref", "po_id", "po_line_id", "receipt_id", "invoice_number", "invoice_refs",
    "payment_reference", "bank_reference", "processor", "tax_amount", "delegation",
    "cost_centre", "quantity", "unit_amount", "vendor_id", "customer_id", "employee_id",
]

#: The business key for a role: the column(s) that identify one record across versions.
KEY_FIELDS: dict[str, tuple[str, ...]] = {
    "chart": ("account",),
    "opening": ("record_id",),
    "ledger": ("entry_id", "line_id"),
    "vendors": ("vendor_id",),
    "purchase_orders": ("po_id", "line_id"),
    "goods_receipts": ("receipt_id", "line_id"),
    "vendor_invoices": ("record_id",),
    "payments": ("payment_id",),
    "customers": ("customer_id",),
    "customer_invoices": ("record_id",),
    "remittances": ("remittance_id",),
    "bank_transactions": ("bank_id",),
    "processor_payouts": ("payout_id",),
    "payroll": ("record_id",),
    "expenses": ("record_id",),
    "budgets": ("record_id",),
    "forecasts": ("record_id",),
    "headcount": ("record_id",),
    "approvals": ("record_id",),
    "period_locks": ("record_id",),
    "tax_registrations": ("record_id",),
}

#: Sentence-case display names. The API value never changes with the label.
LABELS: dict[str, str] = {
    "chart": "Chart of accounts",
    "opening": "Opening trial balance",
    "ledger": "General ledger",
    "vendors": "Vendors",
    "purchase_orders": "Purchase orders",
    "goods_receipts": "Goods receipts",
    "vendor_invoices": "Vendor invoices",
    "payments": "Vendor payments",
    "customers": "Customers",
    "customer_invoices": "Customer invoices",
    "remittances": "Customer remittances",
    "bank_transactions": "Bank transactions",
    "processor_payouts": "Payment processor payouts",
    "payroll": "Payroll",
    "expenses": "Employee expenses",
    "budgets": "Approved budget",
    "forecasts": "Forecast",
    "headcount": "Headcount",
    "approvals": "Approvals",
    "period_locks": "Period locks",
    "tax_registrations": "Tax registrations",
    "contract": "Contracts",
    "policy": "Policies",
    "document": "Other documents",
}

ACCOUNT_TYPES: frozenset[str] = frozenset({"asset", "liability", "equity", "revenue", "expense"})
DIRECTIONS: frozenset[str] = frozenset({"in", "out"})
#: A period label is a month. Quarterly and annual plans are supplied as their months.
PERIOD_PATTERN = r"\d{4}-\d{2}"


def structured_roles() -> list[str]:
    """Every tabular role, in declaration order."""
    return list(FIELDS)


def key_of(role: str, payload: dict) -> str:
    """The business key for one parsed row.

    A composite key is joined with a separator no identifier may contain, so
    ``("PO-1", "2")`` can never collide with ``("PO-1|2",)``.
    """
    parts = [str(payload.get(field, "")) for field in KEY_FIELDS[role]]
    return "\x1f".join(parts)


def row_issues(role: str, payload: dict, config: dict) -> list[tuple[str, str, str | None]]:
    """Role-specific record checks, as ``(code, message, field)``.

    These are arithmetic and domain invariants that can be decided from one row
    plus the workspace period. Anything needing other rows — three-way matching,
    reconciliation, duplicate detection — belongs to the accounting engine and to
    the agents, not here. Intake decides whether a row is *well formed*, never
    whether it is *right*.
    """
    out: list[tuple[str, str, str | None]] = []
    start, end = config["start"], config["end"]

    def money(field: str) -> int:
        return payload.get(field + "_cents", 0)

    if role == "chart" and payload.get("type") not in ACCOUNT_TYPES:
        out.append(("account_type", "Use asset, liability, equity, revenue or expense", "type"))

    if role in {"opening", "ledger"}:
        debit, credit = money("debit"), money("credit")
        if (debit == 0) == (credit == 0):
            out.append(("journal_side", "Exactly one of debit or credit must be positive", None))

    if role == "ledger" and not start <= payload.get("date", "") <= end:
        out.append(("period_mismatch", "Accounting date falls outside the selected period", "date"))

    if role == "opening" and payload.get("balance_date") != start:
        out.append(("opening_date", "Opening balances are dated at the start of the period, before activity", "balance_date"))

    if role == "bank_transactions" and payload.get("direction") not in DIRECTIONS:
        out.append(("bank_direction", "Direction must be in or out; a sign is not accepted", "direction"))

    if role == "processor_payouts":
        # The payout identity is the whole reason this role exists: a net figure
        # that does not decompose cannot be reconciled against gross sales.
        expected = money("gross") - money("fees") - money("refunds") - money("chargebacks")
        if money("net") != expected:
            out.append(("payout_identity",
                        "Net must equal gross less fees, refunds and chargebacks", "net"))

    if role == "payroll":
        if money("gross") - money("deductions") != money("net"):
            out.append(("payroll_tie", "Gross less deductions must equal net", "net"))
        if payload.get("period_end", "") < start or payload.get("period_start", "9999") > end:
            out.append(("period_mismatch", "Pay period does not overlap the workspace period", "period_start"))

    if role == "tax_registrations":
        rate = payload.get("rate_basis_points")
        if isinstance(rate, int) and not 0 <= rate <= 10_000:
            out.append(("rate_range", "A rate in basis points runs from 0 to 10000", "rate_basis_points"))

    # Amount-bearing operational records describe a real obligation or movement.
    if role in {"vendor_invoices", "customer_invoices", "payments", "remittances",
                "purchase_orders", "goods_receipts", "expenses"} and money("amount") <= 0:
        out.append(("nonpositive_amount",
                    "A zero or negative amount is a data error; reversals need their own record", "amount"))

    for earlier, later in (("invoice_date", "due_date"), ("period_start", "period_end"),
                           ("effective_from", "effective_to"), ("registered_from", "registered_to")):
        if payload.get(earlier) and payload.get(later) and payload[earlier] > payload[later]:
            out.append(("date_order", f"{earlier} must not be after {later}", later))

    return out
