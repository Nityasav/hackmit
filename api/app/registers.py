"""Browsing committed records, and exporting a period as a spreadsheet.

Everything here is a pure function over (records, config) — nothing reaches the
database or the network, so a register can be tested as arithmetic over rows.
`app/main.py` supplies the records; this module only chooses and shapes them.

## Why a register needs to say which date it filtered on

Most roles carry several dates that mean genuinely different things. A vendor
invoice has an `invoice_date` and a `due_date`; a payroll run has a
`period_start`, a `period_end` and a `pay_date`. "Everything in September" is
therefore not one question — invoiced in September, due in September and paid
in September are three different registers, and a total taken from the wrong
one is wrong in a way that looks entirely reasonable on screen.

So a filtered register always reports the field it filtered on, and the export
carries it in the filename and a header row. A spreadsheet that has left the
application cannot be re-interrogated about what it means.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from .roles import DATE_FIELDS, FIELDS, LABELS, MONEY_FIELDS

#: The date a person means by default for each role, where one is clearly
#: primary. Absent here, the caller must name the field rather than have one
#: guessed: a register filtered on the wrong date is not a near miss.
PRIMARY_DATE: dict[str, str] = {
    "ledger": "date",
    "opening": "balance_date",
    "purchase_orders": "order_date",
    "goods_receipts": "received_date",
    "vendor_invoices": "invoice_date",
    "customer_invoices": "invoice_date",
    "payments": "payment_date",
    "remittances": "received_date",
    "bank_transactions": "settlement_date",
    "processor_payouts": "payout_date",
    "expenses": "expense_date",
    # payroll is deliberately absent. It carries period_start, period_end and
    # pay_date, and a run worked in one month and paid in the next belongs to a
    # different register under each. Naming the field is a small cost against
    # producing a defensible-looking register of the wrong thing.
    "approvals": "approved_at",
    "period_locks": "locked_at",
    "chart": "effective_from",
    "tax_registrations": "registered_from",
}


def date_fields(role: str) -> list[str]:
    """Every date this role actually carries, in the order its columns read."""
    return [field for field in FIELDS.get(role, []) if field in DATE_FIELDS]


def resolve_field(role: str, field: str | None) -> str:
    """Which date to filter on, refusing to guess when it is ambiguous."""
    available = date_fields(role)
    if not available:
        raise ValueError(f"{LABELS.get(role, role)} records carry no date to filter on")
    if field:
        if field not in available:
            raise ValueError(f"{field!r} is not a date on {LABELS.get(role, role)}; "
                             f"choose one of {', '.join(available)}")
        return field
    primary = PRIMARY_DATE.get(role)
    if primary and primary in available:
        return primary
    if len(available) == 1:
        return available[0]
    raise ValueError(f"{LABELS.get(role, role)} carries several dates "
                     f"({', '.join(available)}); name the one you mean")


def select(records: list[dict], role: str, *, field: str | None = None,
           start: str | None = None, end: str | None = None) -> dict[str, Any]:
    """Records of one role whose chosen date falls within an inclusive range.

    Dates are compared as ISO strings, which intake already normalised and
    validated, so this needs no parsing and cannot drift from what was stored.
    A row missing the field is excluded and counted rather than dropped
    silently: "no payout on that date" and "this row never recorded one" are
    different answers, and only one of them means the books are complete.
    """
    if start and end and start > end:
        raise ValueError("The start of the range falls after its end")
    on = resolve_field(role, field)

    matched, undated = [], 0
    for record in records:
        if record["role"] != role:
            continue
        value = record["payload"].get(on)
        if not value:
            undated += 1
            continue
        if (start and value < start) or (end and value > end):
            continue
        matched.append(record)

    matched.sort(key=lambda r: (r["payload"].get(on) or "", r["record_key"]))
    return {
        "role": role,
        "label": LABELS.get(role, role),
        "filtered_on": on,
        "available_dates": date_fields(role),
        "start": start,
        "end": end,
        "count": len(matched),
        "records_without_this_date": undated,
        "records": matched,
    }


def to_csv(view: dict[str, Any]) -> str:
    """A register as a spreadsheet, carrying what it is on its face.

    The header states the role, the date filtered on and the range, because a
    file that has left the application cannot be asked what it meant — and a
    column of amounts with no stated basis is the kind of thing that ends up
    in a board pack.
    """
    columns = FIELDS.get(view["role"], [])
    if not columns:
        columns = sorted({key for r in view["records"] for key in r["payload"]})

    # Intake stores money as integer cents under `<field>_cents`, so writing the
    # declared column name straight out produced an empty `amount` on every row
    # — which in a finance export reads as zero rather than as a mapping fault.
    # Emitted as an exact decimal string, never a float.
    money = {name: f"{name}_cents" for name in columns if name in MONEY_FIELDS}

    buf = io.StringIO()
    period = f"{view['start'] or 'the earliest record'} to {view['end'] or 'the latest record'}"
    buf.write(f"# {view['label']} · filtered on {view['filtered_on']} · {period}\n")
    buf.write(f"# {view['count']} record(s). Supplied records only; completeness is not verified.\n")
    if view["records_without_this_date"]:
        buf.write(f"# {view['records_without_this_date']} record(s) of this role carry no "
                  f"{view['filtered_on']} and are not included.\n")

    writer = csv.DictWriter(buf, fieldnames=["source_id", "source_line", *columns],
                            extrasaction="ignore")
    writer.writeheader()
    for record in view["records"]:
        row = dict(record["payload"])
        for name, stored in money.items():
            if stored in row:
                row[name] = _decimal_string(row[stored])
        writer.writerow({"source_id": record["source_id"], "source_line": record["locator"], **row})
    return buf.getvalue()


def _decimal_string(cents: Any) -> str:
    """Integer cents as an exact decimal string. No float ever touches money."""
    if cents is None or isinstance(cents, bool) or not isinstance(cents, int):
        return "" if cents is None else str(cents)
    sign = "-" if cents < 0 else ""
    units, remainder = divmod(abs(cents), 100)
    return f"{sign}{units}.{remainder:02d}"


def filename(view: dict[str, Any]) -> str:
    """A name that still says what the file is once it is in a downloads folder."""
    span = "-".join(part for part in (view["start"], view["end"]) if part) or "all"
    return f"{view['role']}-by-{view['filtered_on']}-{span}.csv"
