"""Generate a synthetic SaaS company's books as CSV files on disk.

    python fixtures/generate_saas.py --out ./generated --seed 7 \
        --periods 2026-07 2026-08 2026-09

This writes files. It does not touch the application database, and nothing here is
ever loaded automatically. To use the output you create a workspace in Books, select
these files, map the columns, review the validation and commit a snapshot — exactly as
you would with real records. There is no demo mode and no seeding path, deliberately:
the only way data reaches the product is the way a customer's data would.

Every company, person, vendor and transaction below is fictional.

## How it is built

Clean economic events first, then the books are *derived* from them. An event knows
what happened in the business; the invoice, the receipt, the payment, the bank line and
the journal entries are views of that one event and all carry its `event_ref`. That
column is what lets the import materialize the event graph without guessing, and it is
what the matching engine is later scored against.

Because the books are derived rather than authored, they tie by construction: every
journal balances as it is emitted, the subledgers are the same rows the journals came
from, and `--check` re-proves it from the written files rather than from memory.

`--defects` plants controlled matching and control failures plus benign lookalikes.
The separate truth file records expected classifications; never upload it as evidence.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import json
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

# --------------------------------------------------------------------------- #
# Chart of accounts
# --------------------------------------------------------------------------- #

ACCOUNTS: list[tuple[str, str, str, str]] = [
    ("1000", "Cash", "asset", "cash"),
    ("1100", "Accounts receivable", "asset", "receivables"),
    ("1200", "Prepaid expenses", "asset", "prepaid"),
    ("1300", "Processor receivable", "asset", "receivables"),
    ("1500", "Fixed assets", "asset", "fixed_assets"),
    ("1600", "Accumulated depreciation", "asset", "fixed_assets"),
    ("2000", "Accounts payable", "liability", "payables"),
    ("2100", "Accrued expenses", "liability", "accruals"),
    ("2200", "Payroll liabilities", "liability", "payroll"),
    ("2400", "Sales tax payable", "liability", "tax"),
    ("3000", "Common stock", "equity", "equity"),
    ("3100", "Retained earnings", "equity", "equity"),
    ("4000", "Subscription revenue", "revenue", "revenue"),
    ("4100", "Services revenue", "revenue", "revenue"),
    ("5000", "Cost of revenue", "expense", "cost_of_revenue"),
    ("6000", "Salaries and wages", "expense", "payroll"),
    ("6010", "Employer taxes and benefits", "expense", "payroll"),
    ("6100", "Cloud hosting", "expense", "opex"),
    ("6200", "Software subscriptions", "expense", "opex"),
    ("6300", "Marketing", "expense", "opex"),
    ("6400", "Professional fees", "expense", "opex"),
    ("6500", "Travel", "expense", "opex"),
    ("6600", "Office and admin", "expense", "opex"),
    ("6700", "Payment processing fees", "expense", "opex"),
    ("6800", "Depreciation", "expense", "opex"),
]

CASH, AR, PROCESSOR_AR, AP = "1000", "1100", "1300", "2000"
PAYROLL_LIABILITY, SALES_TAX = "2200", "2400"
SUBSCRIPTION, SERVICES = "4000", "4100"
SALARIES, EMPLOYER_COST, PROCESSING_FEES = "6000", "6010", "6700"

#: Expense accounts a vendor bill may land in, with the spend category that implies.
VENDOR_CATEGORIES: list[tuple[str, str]] = [
    ("6100", "Cloud hosting"), ("6200", "Software"), ("6300", "Marketing"),
    ("6400", "Professional fees"), ("6600", "Office and admin"), ("5000", "Cost of revenue"),
]

DEPARTMENTS = ["Engineering", "Sales", "Marketing", "Customer Success", "General and administrative"]

VENDOR_STEMS = [
    "Northlight", "Kestrel", "Umbra", "Redpoint", "Silverleaf", "Halcyon", "Ironwood",
    "Bluecrest", "Verdant", "Quarry", "Lantern", "Meridian", "Copperfield", "Aster",
    "Tidewater", "Foxglove", "Brightwell", "Cobalt", "Pinnacle", "Harrow",
]
VENDOR_SUFFIXES = ["Systems", "Labs", "Partners", "Group", "Technologies", "Services", "Studio", "Works"]
CUSTOMER_STEMS = [
    "Ashgrove", "Barrowfield", "Calder", "Dunmore", "Eastvale", "Fernbank", "Glenmoor",
    "Havenport", "Ilford", "Jessamine", "Kingsbridge", "Larkspur", "Marchmont",
    "Netherby", "Oakhurst", "Pembroke", "Quillon", "Ravenscourt", "Stonebridge", "Thornbury",
]
CUSTOMER_SUFFIXES = ["Holdings", "Retail", "Logistics", "Media", "Health", "Financial", "Energy"]
GIVEN = ["Amara", "Bo", "Casey", "Devi", "Emil", "Farah", "Gus", "Hana", "Ines", "Jae",
         "Kit", "Lior", "Mira", "Noor", "Otto", "Pia", "Quinn", "Rae", "Sami", "Tove"]
FAMILY = ["Abara", "Baptiste", "Cardoso", "Dawit", "Eriksen", "Fontaine", "Gallo", "Hsu",
          "Ivanov", "Jarrah", "Kovac", "Lindqvist", "Moreau", "Nakamura", "Okafor", "Pires"]


def money(cents: int) -> str:
    """Major units with two decimals, which is what intake parses."""
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


def month_bounds(period: str) -> tuple[date, date]:
    year, month = (int(part) for part in period.split("-"))
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def business_day(day: date) -> date:
    """Nudge weekends forward. Cash does not settle on a Sunday."""
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


# --------------------------------------------------------------------------- #
# The books being built
# --------------------------------------------------------------------------- #

@dataclass
class Books:
    """Row collections plus the journal, which is emitted as events are created."""

    rows: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    journal: list[dict] = field(default_factory=list)
    truth: list[dict] = field(default_factory=list)
    _entry: int = 0

    def add(self, role: str, row: dict) -> None:
        self.rows[role].append(row)

    def post(self, when: date, event_ref: str, memo: str, lines: list[tuple[str, int, int]],
             posted_at: date | None = None) -> str:
        """Write one balanced journal entry. Refuses to emit an unbalanced one.

        `lines` are (account, debit_cents, credit_cents). The balance check happens
        here rather than in a later pass, so a defect can never be an accident.
        """
        debits = sum(line[1] for line in lines)
        credits = sum(line[2] for line in lines)
        if debits != credits:
            raise AssertionError(f"{memo}: debits {debits} != credits {credits}")
        if any(debit < 0 or credit < 0 or bool(debit) == bool(credit) for _, debit, credit in lines):
            raise AssertionError(f"{memo}: every line needs exactly one non-negative side")
        self._entry += 1
        entry_id = f"JE-{self._entry:05d}"
        for index, (account, debit, credit) in enumerate(lines, 1):
            self.add("ledger", {
                "entry_id": entry_id, "line_id": str(index), "date": when.isoformat(),
                "account": account, "debit": money(debit), "credit": money(credit),
                # When the entry was written, as against the date it carries. Normally
                # the same day; a post-close entry is where they differ across a lock.
                "posted_at": (posted_at or when).isoformat(),
                "memo": memo, "event_ref": event_ref,
            })
        return entry_id

    def record_event(self, event_ref: str, kind: str, title: str, when: date,
                     period: str, artifacts: dict[str, list[str]]) -> None:
        self.truth.append({"event_ref": event_ref, "kind": kind, "title": title,
                           "occurred_on": when.isoformat(), "period": period,
                           "artifacts": artifacts})


# --------------------------------------------------------------------------- #
# Static reference data
# --------------------------------------------------------------------------- #

def build_reference(books: Books, rng: random.Random, opened_on: date) -> tuple[list[dict], list[dict], list[dict]]:
    for account, name, kind, mapping in ACCOUNTS:
        books.add("chart", {"account": account, "name": name, "type": kind,
                            "report_mapping": mapping, "effective_from": opened_on.isoformat()})

    vendors = []
    for index in range(40):
        stem = VENDOR_STEMS[index % len(VENDOR_STEMS)]
        suffix = VENDOR_SUFFIXES[(index // len(VENDOR_STEMS) + index) % len(VENDOR_SUFFIXES)]
        account, category = VENDOR_CATEGORIES[index % len(VENDOR_CATEGORIES)]
        vendor = {"vendor_id": f"V-{1000 + index}", "name": f"{stem} {suffix}",
                  "country": rng.choice(["US", "US", "US", "CA", "GB", "DE"]),
                  "payment_terms_days": str(rng.choice([15, 30, 30, 45])),
                  "memo": category}
        vendor["_account"] = account
        vendors.append(vendor)
        books.add("vendors", {k: v for k, v in vendor.items() if not k.startswith("_")})

    customers = []
    for index in range(25):
        stem = CUSTOMER_STEMS[index % len(CUSTOMER_STEMS)]
        suffix = CUSTOMER_SUFFIXES[index % len(CUSTOMER_SUFFIXES)]
        customer = {"customer_id": f"C-{2000 + index}", "name": f"{stem} {suffix}",
                    "country": rng.choice(["US", "US", "US", "CA", "GB"]),
                    "payment_terms_days": str(rng.choice([30, 30, 45, 60]))}
        customers.append(customer)
        books.add("customers", customer)

    employees = []
    for index in range(60):
        department = DEPARTMENTS[index % len(DEPARTMENTS)]
        base = rng.randrange(7_500_00, 16_000_00, 5_00)
        employees.append({
            "employee_id": f"E-{3000 + index}",
            "name": f"{GIVEN[index % len(GIVEN)]} {FAMILY[(index * 7) % len(FAMILY)]}",
            "department": department, "monthly_gross_cents": base,
        })
    return vendors, customers, employees


def build_opening(books: Books, period_start: date, cash: int, receivables: int, payables: int) -> None:
    """A balanced opening trial balance, dated before any activity.

    Receivables and payables are *derived* from the invoices carried into the period
    rather than invented, so the opening subledger balances agree with the open items
    listed beside them. Retained earnings is the balancing figure, which is what makes
    the statement tie without a plug line.
    """
    equity = cash + receivables - payables
    lines = [(CASH, cash, 0), (AR, receivables, 0), (AP, 0, payables), ("3100", 0, equity)]
    for index, (account, debit, credit) in enumerate(lines, 1):
        books.add("opening", {
            "record_id": f"OB-{index:03d}", "account": account,
            "balance_date": period_start.isoformat(),
            "debit": money(debit), "credit": money(credit),
        })


# --------------------------------------------------------------------------- #
# Period activity
# --------------------------------------------------------------------------- #

def purchase_cycle(books, rng, period, start, end, vendors, counter) -> int:
    """Purchase order, goods receipt, vendor invoice and the payment that settles it.

    Bills are dated across a window that reaches back before the period, because that
    is how payables actually behave: what you pay this month was mostly billed last
    month. A bill dated before the period is carried-in AP — its subledger rows exist
    and it can be paid in-period, but its expense belongs to the prior period, so no
    journal is posted for it here. The function returns that carried-in total, which
    becomes the opening payables balance.
    """
    carried_in = 0
    # 26 billed inside the period, 14 carried in, for the same reason as sales: the
    # first set is the month's cost, the second is opening payables to pay down.
    for index in range(40):
        in_period = index < 26
        vendor = rng.choice(vendors)
        ordered = business_day(start + timedelta(
            days=rng.randrange(0, 12) if in_period else rng.randrange(-45, -12)))
        received = business_day(ordered + timedelta(days=rng.randrange(1, 8)))
        billed = business_day(received + timedelta(days=rng.randrange(0, 5)))
        amount = rng.randrange(45_000, 2_400_000, 100)
        counter["n"] += 1
        n = counter["n"]
        ref = f"EVT-{period}-P{n:04d}"
        po_id, receipt_id = f"PO-{7000 + n}", f"GR-{8000 + n}"
        invoice_id, invoice_number = f"VI-{9000 + n}", f"INV-{20000 + n}"
        # The person who raises the order and the person who approves paying it must
        # be different, or the segregation-of-duties control fires on every invoice and
        # a real breach becomes indistinguishable from the baseline. Phase 4 plants the
        # exceptions; the clean period must not come with one built in.
        requester = f"{GIVEN[n % len(GIVEN)]} {FAMILY[n % len(FAMILY)]}"
        approver = f"{GIVEN[(n + 7) % len(GIVEN)]} {FAMILY[(n + 5) % len(FAMILY)]}"
        assert requester != approver

        books.add("purchase_orders", {
            "po_id": po_id, "line_id": "1", "vendor_id": vendor["vendor_id"],
            "description": vendor["memo"], "order_date": ordered.isoformat(),
            "amount": money(amount), "approver": requester, "event_ref": ref})
        books.add("goods_receipts", {
            "receipt_id": receipt_id, "line_id": "1", "po_id": po_id, "po_line_id": "1",
            "received_date": received.isoformat(), "amount": money(amount), "event_ref": ref})
        due = billed + timedelta(days=int(vendor["payment_terms_days"]))
        books.add("vendor_invoices", {
            "record_id": invoice_id, "vendor_id": vendor["vendor_id"],
            "invoice_number": invoice_number, "invoice_date": billed.isoformat(),
            "due_date": due.isoformat(), "amount": money(amount),
            "po_id": po_id, "receipt_id": receipt_id, "event_ref": ref})
        if billed >= start:
            books.post(billed, ref, f"Vendor bill {invoice_number}",
                       [(vendor["_account"], amount, 0), (AP, 0, amount)])
        else:
            # Prior-period expense. It sits in opening payables, not in this period's
            # profit; posting it again here would overstate the month.
            carried_in += amount
        books.add("approvals", {
            "record_id": f"AP-{n:05d}", "actor": approver, "authority": "Delegated authority",
            "action": "approve_invoice", "target_type": "vendor_invoice", "target_id": invoice_id,
            "approved_at": billed.isoformat(), "event_ref": ref})

        artifacts = {"purchase_orders": [po_id], "goods_receipts": [receipt_id],
                     "vendor_invoices": [invoice_id]}
        # Bills due inside the period are paid inside it; the rest stay in payables.
        if start <= due <= end:
            paid = business_day(due)
            payment_id, reference = f"PMT-{11000 + n}", f"ACH-{500000 + n}"
            books.add("payments", {
                "payment_id": payment_id, "vendor_id": vendor["vendor_id"],
                "payment_date": paid.isoformat(), "method": "ach", "amount": money(amount),
                "reference": reference, "invoice_number": invoice_number, "event_ref": ref})
            books.post(paid, ref, f"Payment {reference}", [(AP, amount, 0), (CASH, 0, amount)])
            books.add("bank_transactions", {
                "bank_id": f"BK-{600000 + n}", "bank_account": "Operating",
                "settlement_date": paid.isoformat(), "direction": "out", "amount": money(amount),
                "description": f"ACH DEBIT {vendor['name'][:18].upper()}",
                "bank_reference": reference, "event_ref": ref})
            artifacts["payments"] = [payment_id]
        books.record_event(ref, "purchase", f"{vendor['name']} — {vendor['memo']}", billed, period, artifacts)

    # Deliveries late in the month whose invoice has not arrived yet. Entirely ordinary
    # at a period end, and the reason accruals exist: the cost belongs to this period
    # and no bill names it. Nothing is posted for them, which is what leaves the month
    # understated until someone accrues it.
    for _ in range(4):
        vendor = rng.choice(vendors)
        ordered = business_day(end - timedelta(days=rng.randrange(9, 16)))
        received = business_day(ordered + timedelta(days=rng.randrange(1, 5)))
        amount = rng.randrange(180_000, 900_000, 100)
        counter["n"] += 1
        n = counter["n"]
        ref = f"EVT-{period}-U{n:04d}"
        po_id, receipt_id = f"PO-{7000 + n}", f"GR-{8000 + n}"
        books.add("purchase_orders", {
            "po_id": po_id, "line_id": "1", "vendor_id": vendor["vendor_id"],
            "description": vendor["memo"], "order_date": ordered.isoformat(),
            "amount": money(amount),
            "approver": f"{GIVEN[n % len(GIVEN)]} {FAMILY[n % len(FAMILY)]}",
            "event_ref": ref})
        books.add("goods_receipts", {
            "receipt_id": receipt_id, "line_id": "1", "po_id": po_id, "po_line_id": "1",
            "received_date": received.isoformat(), "amount": money(amount),
            "event_ref": ref})
        books.record_event(ref, "purchase", f"{vendor['name']} — delivered, not yet billed",
                           received, period,
                           {"purchase_orders": [po_id], "goods_receipts": [receipt_id]})

    return carried_in


def sales_cycle(books, rng, period, start, end, customers, counter) -> int:
    """Customer invoice and the remittance that settles it.

    Same shape as payables and for the same reason: cash collected this month settles
    invoices issued one to two months ago, because terms run thirty to sixty days.
    Issuing only in-period would mean receivables were never collected and the bank
    reconciliation would have no credits to match. Returns carried-in receivables.
    """
    carried_in = 0
    # 22 billed inside the period, 14 carried in. The first set is the month's services
    # revenue; the second is opening receivables with something to collect against.
    for index in range(36):
        in_period = index < 22
        customer = rng.choice(customers)
        issued = business_day(start + timedelta(
            days=rng.randrange(0, 20) if in_period else rng.randrange(-60, -5)))
        amount = rng.randrange(400_000, 3_200_000, 100)
        tax = amount * 725 // 10_000 if customer["country"] == "US" else 0
        counter["n"] += 1
        n = counter["n"]
        ref = f"EVT-{period}-S{n:04d}"
        invoice_id, invoice_number = f"CI-{12000 + n}", f"SI-{30000 + n}"
        due = issued + timedelta(days=int(customer["payment_terms_days"]))
        books.add("customer_invoices", {
            "record_id": invoice_id, "customer_id": customer["customer_id"],
            "invoice_number": invoice_number, "invoice_date": issued.isoformat(),
            "due_date": due.isoformat(), "amount": money(amount + tax),
            "tax_amount": money(tax), "event_ref": ref})
        if issued >= start:
            lines = [(AR, amount + tax, 0), (SERVICES, 0, amount)]
            if tax:
                lines.append((SALES_TAX, 0, tax))
            books.post(issued, ref, f"Customer invoice {invoice_number}", lines)
        else:
            # Prior-period revenue, already earned. It arrives as opening receivables.
            carried_in += amount + tax

        artifacts = {"customer_invoices": [invoice_id]}
        if start <= due <= end:
            received = business_day(due)
            remittance_id, reference = f"RM-{13000 + n}", f"WIRE-{700000 + n}"
            books.add("remittances", {
                "remittance_id": remittance_id, "customer_id": customer["customer_id"],
                "received_date": received.isoformat(), "amount": money(amount + tax),
                "reference": reference, "invoice_refs": invoice_number, "event_ref": ref})
            books.post(received, ref, f"Cash applied {reference}",
                       [(CASH, amount + tax, 0), (AR, 0, amount + tax)])
            books.add("bank_transactions", {
                "bank_id": f"BK-{610000 + n}", "bank_account": "Operating",
                "settlement_date": received.isoformat(), "direction": "in",
                "amount": money(amount + tax),
                "description": f"WIRE CREDIT {customer['name'][:18].upper()}",
                "bank_reference": reference, "event_ref": ref})
            artifacts["remittances"] = [remittance_id]
        books.record_event(ref, "sale", f"{customer['name']} — services", issued, period, artifacts)
    return carried_in


def processor_cycle(books, rng, period, start, end, counter):
    """Self-serve subscriptions settle through a processor, net of its deductions.

    Two events: the month's gross sales accrue to a processor receivable, and the
    payout clears it. Keeping them separate is the point — a payout that arrives net
    cannot be reconciled against gross sales unless the deductions are recorded.
    """
    for index in range(2):
        counter["n"] += 1
        n = counter["n"]
        ref = f"EVT-{period}-X{n:04d}"
        paid_out = business_day(start + timedelta(days=14 * index + 12))
        gross = rng.randrange(28_000_000, 44_000_000, 100)
        fees = gross * rng.randrange(210, 310) // 10_000
        refunds = rng.randrange(0, gross // 40, 100)
        chargebacks = rng.randrange(0, gross // 200, 100)
        net = gross - fees - refunds - chargebacks

        books.post(paid_out, ref, "Subscription sales via processor",
                   [(PROCESSOR_AR, gross, 0), (SUBSCRIPTION, 0, gross)])
        payout_id, reference = f"PO-{14000 + n}", f"PAYOUT-{800000 + n}"
        books.add("processor_payouts", {
            "payout_id": payout_id, "processor": "card_processor",
            "payout_date": paid_out.isoformat(), "gross": money(gross), "fees": money(fees),
            "refunds": money(refunds), "chargebacks": money(chargebacks), "net": money(net),
            "bank_reference": reference, "event_ref": ref})
        lines = [(CASH, net, 0), (PROCESSING_FEES, fees, 0)]
        if refunds:
            lines.append((SUBSCRIPTION, refunds, 0))
        if chargebacks:
            lines.append((SUBSCRIPTION, chargebacks, 0))
        lines.append((PROCESSOR_AR, 0, gross))
        books.post(paid_out, ref, f"Processor payout {reference}", lines)
        books.add("bank_transactions", {
            "bank_id": f"BK-{620000 + n}", "bank_account": "Operating",
            "settlement_date": paid_out.isoformat(), "direction": "in", "amount": money(net),
            "description": "CARD PROCESSOR PAYOUT", "bank_reference": reference, "event_ref": ref})
        books.record_event(ref, "processor_payout", "Card processor settlement", paid_out, period,
                           {"processor_payouts": [payout_id]})


def payroll_cycle(books, rng, period, start, end, employees, counter):
    """One monthly payroll run: gross less deductions is what leaves the bank."""
    pay_date = business_day(end - timedelta(days=2))
    counter["n"] += 1
    ref = f"EVT-{period}-R{counter['n']:04d}"
    total_gross = total_deductions = total_employer = 0
    for index, employee in enumerate(employees):
        gross = employee["monthly_gross_cents"]
        deductions = gross * rng.randrange(2200, 3100) // 10_000
        employer = gross * 1150 // 10_000
        total_gross += gross
        total_deductions += deductions
        total_employer += employer
        books.add("payroll", {
            "record_id": f"PR-{period}-{index:03d}", "employee_id": employee["employee_id"],
            "period_start": start.isoformat(), "period_end": end.isoformat(),
            "pay_date": pay_date.isoformat(), "gross": money(gross),
            "deductions": money(deductions), "net": money(gross - deductions),
            "employer_cost": money(employer), "department": employee["department"],
            # One pay run, one bank debit: every line of the register shares the batch
            # reference, and the bank sees their net total.
            "bank_reference": f"PAYRUN-{period}", "event_ref": ref})
    net = total_gross - total_deductions
    books.post(pay_date, ref, "Payroll", [
        (SALARIES, total_gross, 0), (EMPLOYER_COST, total_employer, 0),
        (CASH, 0, net), (PAYROLL_LIABILITY, 0, total_deductions + total_employer)])
    books.add("bank_transactions", {
        "bank_id": f"BK-{630000 + counter['n']}", "bank_account": "Operating",
        "settlement_date": pay_date.isoformat(), "direction": "out", "amount": money(net),
        "description": "PAYROLL ACH BATCH", "bank_reference": f"PAYRUN-{period}", "event_ref": ref})
    books.record_event(ref, "payroll", f"Payroll {period}", pay_date, period,
                       {"payroll": [f"PR-{period}-{i:03d}" for i in range(len(employees))]})
    for department in DEPARTMENTS:
        books.add("headcount", {
            "record_id": f"HC-{period}-{department[:3].upper()}", "department": department,
            "period": period, "count": str(sum(e["department"] == department for e in employees))})


def expense_cycle(books, rng, period, start, end, employees, counter):
    categories = [("6500", "Travel"), ("6600", "Office and admin"), ("6300", "Marketing")]
    for _ in range(25):
        employee = rng.choice(employees)
        account, category = rng.choice(categories)
        spent = business_day(start + timedelta(days=rng.randrange(0, 25)))
        amount = rng.randrange(2_500, 180_000, 25)
        counter["n"] += 1
        n = counter["n"]
        ref = f"EVT-{period}-E{n:04d}"
        record_id = f"EX-{15000 + n}"
        books.add("expenses", {
            "record_id": record_id, "employee_id": employee["employee_id"],
            "expense_date": spent.isoformat(), "category": category, "amount": money(amount),
            "merchant": f"{rng.choice(VENDOR_STEMS)} {rng.choice(VENDOR_SUFFIXES)}",
            "department": employee["department"],
            # The card reference the statement will show. Without it the expense cannot
            # be traced to its bank line, and the line reports as unexplained.
            "bank_reference": record_id, "event_ref": ref})
        books.post(spent, ref, f"Expense {record_id}", [(account, amount, 0), (CASH, 0, amount)])
        books.add("bank_transactions", {
            "bank_id": f"BK-{640000 + n}", "bank_account": "Operating",
            "settlement_date": spent.isoformat(), "direction": "out", "amount": money(amount),
            "description": f"CARD {category.upper()}", "bank_reference": record_id, "event_ref": ref})
        books.record_event(ref, "expense", f"{category} — {employee['name']}", spent, period,
                           {"expenses": [record_id]})


def plan_rows(books, rng, period, actuals_by_account):
    """A budget and a prior forecast that are near the actuals but not equal to them.

    Variance analysis needs something to differ from. The spread is deliberate and
    unlabelled: nothing in the output says which accounts were set high or low.
    """
    for account, name, kind, _ in ACCOUNTS:
        if kind != "expense":
            continue
        actual = actuals_by_account.get(account, 0)
        if not actual:
            continue
        budget = actual * rng.randrange(8_600, 11_400) // 10_000
        forecast = actual * rng.randrange(9_200, 10_800) // 10_000
        books.add("budgets", {
            "record_id": f"BU-{period}-{account}", "account": account, "period": period,
            "amount": money(budget - budget % 100), "approval_reference": f"BOARD-{period[:4]}-01"})
        books.add("forecasts", {
            "record_id": f"FC-{period}-{account}", "account": account, "period": period,
            "amount": money(forecast - forecast % 100), "basis": "prior period run rate"})


def documents(out: Path) -> None:
    (out / "policy_expense.md").write_text(
        "# Expense and approval policy\n\n"
        "## Approval authority\n\n"
        "- Purchases up to 5,000.00 USD: department lead.\n"
        "- Purchases above 5,000.00 USD: finance director.\n"
        "- Purchases above 50,000.00 USD: two approvers, one an officer.\n"
        "- No person may approve a payment to a counterparty they requested.\n\n"
        "## Supporting evidence\n\n"
        "- A vendor invoice is payable once matched to a purchase order and a goods receipt.\n"
        "- Any invoice without a purchase order is held for review.\n"
        "- A change to vendor bank details requires out-of-band verification before the next payment.\n\n"
        "## Travel and entertainment\n\n"
        "- Meals are reimbursable to 150.00 USD per person per day.\n"
        "- Air travel is booked in economy for flights under six hours.\n"
        "- Receipts are required for any expense above 25.00 USD.\n",
        encoding="utf-8")
    (out / "contract_master_services.md").write_text(
        "# Master services agreement (template)\n\n"
        "## 1. Term\n\n"
        "This agreement runs for twelve months from the effective date and renews for\n"
        "successive twelve-month terms unless either party gives sixty days notice.\n\n"
        "## 2. Fees and invoicing\n\n"
        "Subscription fees are invoiced monthly in arrears and payable within the term\n"
        "stated on the invoice. Professional services are invoiced on delivery of the\n"
        "milestone described in the applicable statement of work.\n\n"
        "## 3. Taxes\n\n"
        "Fees are exclusive of indirect taxes. Where the supplier is registered in the\n"
        "customer's jurisdiction, the applicable tax is shown separately on the invoice.\n\n"
        "## 4. Revenue recognition note\n\n"
        "Subscription fees are earned rateably across the service month. A milestone fee\n"
        "is earned on acceptance, which is the date recorded on the delivery note.\n",
        encoding="utf-8")


# --------------------------------------------------------------------------- #
# Controlled defects
# --------------------------------------------------------------------------- #
#
# Each defect ships with a **benign lookalike**: something that resembles it closely and
# must not be reported. Recall alone is easy — a check that flags everything catches
# every defect — so the lookalikes are what make the measurement mean anything.
#
# Nothing here encodes its own answer. No filename, id, memo or description says
# "defect", because a detector that can read the label is not being tested. The truth
# file is written separately and lives outside anything the application can reach.


def plant_defects(books: Books, rng, period, start, end, vendors, customers, employees, counter):
    """Inject controlled defects and their lookalikes. Returns truth records.

    Called after the clean period is built, so every defect is a modification of
    something that already balanced. The journals stay balanced: a defect is a control
    or matching failure, not a broken ledger, and an unbalanced one would be caught by
    intake before any agent saw it.
    """
    truth: list[dict] = []

    def approve(invoice, actor):
        """Give a planted invoice the approval a real one would carry."""
        counter["n"] += 1
        books.add("approvals", {
            "record_id": f"AP-P{counter['n']:05d}", "actor": actor,
            "authority": "Delegated authority", "action": "approve_invoice",
            "target_type": "vendor_invoice", "target_id": invoice["record_id"],
            "approved_at": invoice["invoice_date"], "event_ref": invoice["event_ref"]})

    def planted(issue_id, family, expectation, record_keys, note):
        truth.append({"issue_id": issue_id, "family": family, "period": period,
                      "expected": expectation, "record_keys": record_keys, "note": note})

    def lookalike(issue_id, family, record_keys, note):
        truth.append({"issue_id": issue_id, "family": family, "period": period,
                      "expected": "clear", "record_keys": record_keys, "note": note})

    orders = books.rows["purchase_orders"]
    approvals = books.rows["approvals"]
    # Only bills dated inside the period can carry a defect: a carried-in bill's expense
    # belongs to the prior period, so a journal copying it would fall outside this one
    # and intake would refuse the whole import before any control test ran.
    invoices = [i for i in books.rows["vendor_invoices"]
                if i["invoice_date"] >= start.isoformat()]
    assert len(invoices) >= 12, "not enough in-period bills to plant against"

    # --- 1. Duplicate invoice, under an altered number ---------------------
    # The same obligation billed twice. The number differs by one character, so an
    # exact-key test on vendor+number+amount will NOT see it: that is the point. The
    # exact-key duplicate below is what the current test does catch.
    original = invoices[3]
    counter["n"] += 1
    twin = dict(original)
    twin["record_id"] = f"VI-D{counter['n']}"
    twin["invoice_number"] = original["invoice_number"] + "-A"
    twin["event_ref"] = original["event_ref"]
    books.add("vendor_invoices", twin)
    approve(twin, "Pia Moreau")
    books.post(date.fromisoformat(original["invoice_date"]), original["event_ref"],
               f"Vendor bill {twin['invoice_number']}",
               [("6100", cents(original["amount"]), 0), (AP, 0, cents(original["amount"]))])
    planted("dup-invoice-altered-number", "duplicate_invoice", "attention",
            [twin["record_id"], original["record_id"]],
            "Same vendor, date and amount under a number one character apart. An "
            "exact-key test does not see this; it needs fuzzy matching on number.")

    # An exact-key duplicate, which the current test does catch.
    counter["n"] += 1
    exact = dict(original)
    exact["record_id"] = f"VI-D{counter['n']}"
    books.add("vendor_invoices", exact)
    approve(exact, "Rae Nakamura")
    books.post(date.fromisoformat(original["invoice_date"]), original["event_ref"],
               f"Vendor bill {exact['invoice_number']} (second copy)",
               [("6100", cents(original["amount"]), 0), (AP, 0, cents(original["amount"]))])
    planted("dup-invoice-exact", "duplicate_invoice", "attention",
            [exact["record_id"], original["record_id"]],
            "Identical vendor, invoice number, amount and currency on two records.")

    # Lookalike: same vendor, same amount, different number and a separate delivery.
    # Two real deliveries of the same thing are not a duplicate.
    counter["n"] += 1
    separate = dict(invoices[5])
    separate["record_id"] = f"VI-L{counter['n']}"
    separate["invoice_number"] = f"INV-9{counter['n']:04d}"
    separate["amount"] = invoices[5]["amount"]
    separate["invoice_date"] = (date.fromisoformat(invoices[5]["invoice_date"])
                                + timedelta(days=9)).isoformat()
    separate["due_date"] = (date.fromisoformat(separate["invoice_date"])
                            + timedelta(days=30)).isoformat()
    books.add("vendor_invoices", separate)
    approve(separate, "Tove Okafor")
    books.post(date.fromisoformat(separate["invoice_date"]), separate["event_ref"],
               f"Vendor bill {separate['invoice_number']}",
               [("6100", cents(separate["amount"]), 0), (AP, 0, cents(separate["amount"]))])
    lookalike("dup-invoice-lookalike", "duplicate_invoice", [separate["record_id"]],
              "Same vendor and amount, different number and date: a second delivery, "
              "not a repeat of the first.")

    # --- 2. Self-approval, and a properly delegated one --------------------
    target = invoices[7]
    order = next((o for o in orders if o["po_id"] == target.get("po_id")), None)
    if order:
        for approval in approvals:
            if approval["target_id"] == target["record_id"]:
                approval["actor"] = order["approver"]
                planted("self-approval", "segregation_of_duties", "attention",
                        [target["record_id"]],
                        "The person who raised the order also approved paying the "
                        "invoice, with no delegation recorded.")
                break

    # Lookalike: the same overlap, but with the delegation that authorizes it.
    delegated_target = invoices[9]
    delegated_order = next((o for o in orders if o["po_id"] == delegated_target.get("po_id")), None)
    if delegated_order:
        for approval in approvals:
            if approval["target_id"] == delegated_target["record_id"]:
                approval["actor"] = delegated_order["approver"]
                approval["delegation"] = "Board delegation 2026-04, finance director absent"
                lookalike("self-approval-delegated", "segregation_of_duties",
                          [delegated_target["record_id"]],
                          "Requester and approver are the same person, and a recorded "
                          "delegation authorizes it.")
                break

    # --- 3. Duplicate vendor ------------------------------------------------
    source_vendor = vendors[2]
    counter["n"] += 1
    twin_vendor = {
        "vendor_id": f"V-D{counter['n']}",
        # Same counterparty, written the way a second system would spell it.
        "name": source_vendor["name"].replace(" Systems", " Systems, Inc."),
        "country": source_vendor["country"],
        "payment_terms_days": source_vendor["payment_terms_days"],
    }
    books.add("vendors", twin_vendor)
    planted("duplicate-vendor", "duplicate_vendor", "attention",
            [twin_vendor["vendor_id"], source_vendor["vendor_id"]],
            "One counterparty under two ids, differing only by a legal suffix.")

    # Lookalike: two genuinely different companies with similar names.
    counter["n"] += 1
    books.add("vendors", {
        "vendor_id": f"V-L{counter['n']}", "name": "Northlight Partners",
        "country": "US", "payment_terms_days": "30"})
    lookalike("duplicate-vendor-lookalike", "duplicate_vendor", [f"V-L{counter['n']}"],
              "Shares a first word with another vendor and is a different company.")

    # --- 4. Entry written after the period was locked -----------------------
    # Dated the 28th, written twelve days after the close. Nothing about the date is
    # unusual; the posting timestamp is the whole finding.
    counter["n"] += 1
    late_ref = f"EVT-{period}-Z{counter['n']:04d}"
    entry_id = books.post(end - timedelta(days=2), late_ref, "Accrual adjustment",
                          [("6400", 450_000, 0), ("2100", 0, 450_000)],
                          posted_at=end + timedelta(days=12))
    # A ledger record is keyed on (entry_id, line_id), so the truth has to name the
    # lines rather than the journal, or scoring finds no overlap and reads as a miss.
    planted("post-close-entry", "post_close", "attention",
            [f"{entry_id}1", f"{entry_id}2"],
            "Dated inside the period and written after the lock on it.")

    # --- 5. Round-number payment -------------------------------------------
    counter["n"] += 1
    round_ref = f"EVT-{period}-Z{counter['n']:04d}"
    round_amount = 2_500_000
    vendor = vendors[11]
    books.add("payments", {
        "payment_id": f"PMT-R{counter['n']}", "vendor_id": vendor["vendor_id"],
        "payment_date": business_day(start + timedelta(days=18)).isoformat(),
        "method": "wire", "amount": money(round_amount),
        "reference": f"WIRE-R{counter['n']}", "event_ref": round_ref})
    books.post(business_day(start + timedelta(days=18)), round_ref, "Round payment",
               [(AP, round_amount, 0), (CASH, 0, round_amount)])
    books.add("bank_transactions", {
        "bank_id": f"BK-R{counter['n']}", "bank_account": "Operating",
        "settlement_date": business_day(start + timedelta(days=18)).isoformat(),
        "direction": "out", "amount": money(round_amount),
        "description": "WIRE DEBIT", "bank_reference": f"WIRE-R{counter['n']}",
        "event_ref": round_ref})
    planted("round-payment", "round_number", "attention", [f"PMT-R{counter['n']}"],
            "An exactly round wire at a size where that is unusual. Weak on its own.")

    return truth


# --------------------------------------------------------------------------- #
# Writing and checking
# --------------------------------------------------------------------------- #

def write_csv(path: Path, rows: list[dict]) -> None:
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def cents(value: str) -> int:
    negative = value.startswith("-")
    whole, _, fraction = value.lstrip("-").partition(".")
    total = int(whole) * 100 + int((fraction or "0").ljust(2, "0")[:2])
    return -total if negative else total


def check(period_dir: Path) -> list[str]:
    """Re-prove the invariants from the written files, not from memory."""
    problems = []

    def read(name):
        path = period_dir / f"{name}.csv"
        if not path.exists():
            return []
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    entries = defaultdict(list)
    for row in read("ledger"):
        entries[row["entry_id"]].append(row)
    for entry_id, lines in entries.items():
        if sum(cents(l["debit"]) - cents(l["credit"]) for l in lines):
            problems.append(f"{entry_id} does not balance")
        if len({l["date"] for l in lines}) > 1:
            problems.append(f"{entry_id} spans more than one date")

    opening = read("opening")
    if opening and sum(cents(r["debit"]) - cents(r["credit"]) for r in opening):
        problems.append("opening trial balance does not balance")

    for row in read("payroll"):
        if cents(row["gross"]) - cents(row["deductions"]) != cents(row["net"]):
            problems.append(f"payroll {row['record_id']} does not tie")

    for row in read("processor_payouts"):
        expected = cents(row["gross"]) - cents(row["fees"]) - cents(row["refunds"]) - cents(row["chargebacks"])
        if cents(row["net"]) != expected:
            problems.append(f"payout {row['payout_id']} does not decompose")

    accounts = {row["account"] for row in read("chart")}
    for row in read("ledger") + read("budgets") + read("forecasts"):
        if row["account"] not in accounts:
            problems.append(f"account {row['account']} is not in the chart")

    # Every artifact must name an event, or the graph cannot be assembled on import.
    for name in ("vendor_invoices", "payments", "customer_invoices", "remittances",
                 "bank_transactions", "processor_payouts", "expenses"):
        for row in read(name):
            if not row.get("event_ref"):
                problems.append(f"{name} row without an event_ref")
                break
    return problems


def generate_period(books: Books, rng, period, vendors, customers, employees, counter,
                    cash: int, defects: bool = False) -> list[dict]:
    start, end = month_bounds(period)
    # Activity first: the opening balances are whatever the period carried in, so they
    # cannot be written until the carried-in population is known.
    payables = purchase_cycle(books, rng, period, start, end, vendors, counter)
    receivables = sales_cycle(books, rng, period, start, end, customers, counter)
    build_opening(books, start, cash=cash, receivables=receivables, payables=payables)
    processor_cycle(books, rng, period, start, end, counter)
    payroll_cycle(books, rng, period, start, end, employees, counter)
    expense_cycle(books, rng, period, start, end, employees, counter)

    actuals = defaultdict(int)
    for row in books.rows["ledger"]:
        actuals[row["account"]] += cents(row["debit"]) - cents(row["credit"])
    plan_rows(books, rng, period, actuals)
    books.add("period_locks", {"record_id": f"LK-{period}", "period": period,
                               "locked_at": (end + timedelta(days=5)).isoformat(),
                               "locked_by": "finance.director"})
    # Defects are injected last, into books that already balance, so every one of them
    # is a control or matching failure rather than a broken ledger.
    return plant_defects(books, rng, period, start, end, vendors, customers,
                         employees, counter) if defects else []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("generated"))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--periods", nargs="+", default=["2026-07", "2026-08", "2026-09"])
    parser.add_argument("--company", default="Halden Cloud Inc.", help="Fictional. Used in the tax registration only.")
    parser.add_argument("--defects", action="store_true",
                        help="Plant controlled defects and their benign lookalikes. The "
                             "truth file records which is which; the records themselves "
                             "never say.")
    parser.add_argument("--check", action="store_true", default=True)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    # Kept beside the data, never inside it: the truth file must not sit anywhere the
    # API serves from or the tool gateway can reach.
    truth_dir = args.out / "truth"
    truth_dir.mkdir(exist_ok=True)

    opened_on = month_bounds(args.periods[0])[0] - timedelta(days=365)
    counter = {"n": 0}
    reference_books = Books()
    vendors, customers, employees = build_reference(reference_books, rng, opened_on)

    problems: list[str] = []
    for index, period in enumerate(args.periods):
        start, _ = month_bounds(period)
        books = Books()
        build_reference(books, random.Random(args.seed), opened_on)
        books.add("tax_registrations", {
            "record_id": "TR-001", "jurisdiction": "US-CA", "tax_type": "sales_tax",
            "rate_basis_points": "725", "registered_from": opened_on.isoformat(),
            "memo": args.company})
        planted = generate_period(books, rng, period, vendors, customers, employees,
                                  counter, cash=rng.randrange(40_000_000, 90_000_000, 100),
                                  defects=args.defects)

        period_dir = args.out / period
        period_dir.mkdir(exist_ok=True)
        for role, rows in sorted(books.rows.items()):
            write_csv(period_dir / f"{role}.csv", rows)
        documents(period_dir)
        (truth_dir / f"{period}.json").write_text(
            json.dumps({"period": period, "seed": args.seed, "events": books.truth,
                        "planted": planted}, indent=2), encoding="utf-8")

        found = check(period_dir) if args.check else []
        problems += [f"{period}: {p}" for p in found]
        total = sum(len(rows) for rows in books.rows.values())
        note = ""
        if planted:
            defects = sum(1 for t in planted if t["expected"] != "clear")
            note = f"  [{defects} defect(s), {len(planted) - defects} lookalike(s)]"
        print(f"{period}: {total:>5} rows across {len(books.rows)} files -> {period_dir}"
              + note + ("" if not found else f"  [{len(found)} PROBLEM(S)]"))

    print(f"\ntruth written to {truth_dir} — keep this out of the API data directory")
    if problems:
        print("\nfailed:")
        for problem in problems[:20]:
            print("  " + problem)
        return 1
    print("all periods tie: journals balance, opening balances, payroll ties, payouts decompose")
    print("\nUpload these through Books. Nothing is seeded and nothing loads automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
