"""Finding specific transactions, and exporting a period.

Pure functions over (records, config): no database, no network. The register
is arithmetic over rows and is tested as arithmetic.

The recurring hazard is that most roles carry several dates meaning different
things — invoiced, due and paid are three different questions — so a total
taken from the wrong one is wrong in a way that looks entirely reasonable.
"""

from __future__ import annotations

import pytest

from app import registers


def _record(role, key, payload, source="source-1", line=2):
    return {"role": role, "record_key": key, "payload": payload,
            "source_id": source, "locator": line}


PAYOUTS = [
    _record("processor_payouts", "PO-1", {"payout_id": "PO-1", "payout_date": "2026-09-15",
                                          "amount": "1200.00"}, line=2),
    _record("processor_payouts", "PO-2", {"payout_id": "PO-2", "payout_date": "2026-09-15",
                                          "amount": "300.00"}, line=3),
    _record("processor_payouts", "PO-3", {"payout_id": "PO-3", "payout_date": "2026-09-16",
                                          "amount": "50.00"}, line=4),
    _record("payments", "PAY-1", {"payment_id": "PAY-1", "payment_date": "2026-09-15"}),
]


def test_every_payout_on_one_specific_date():
    view = registers.select(PAYOUTS, "processor_payouts",
                            start="2026-09-15", end="2026-09-15")

    assert view["count"] == 2
    assert [r["record_key"] for r in view["records"]] == ["PO-1", "PO-2"]
    # Another role's record sharing that date is not a payout.
    assert all(r["role"] == "processor_payouts" for r in view["records"])


def test_the_register_says_which_date_it_filtered_on():
    """Without this the reader cannot tell invoiced-in-September from
    paid-in-September, and the two are different registers."""
    view = registers.select(PAYOUTS, "processor_payouts", start="2026-09-15")
    assert view["filtered_on"] == "payout_date"


def test_a_role_with_several_dates_filters_on_the_one_asked_for():
    invoices = [
        _record("vendor_invoices", "VI-1", {"invoice_date": "2026-09-01", "due_date": "2026-10-01"}),
        _record("vendor_invoices", "VI-2", {"invoice_date": "2026-10-01", "due_date": "2026-11-01"}),
    ]

    invoiced = registers.select(invoices, "vendor_invoices", field="invoice_date",
                                start="2026-10-01", end="2026-10-31")
    due = registers.select(invoices, "vendor_invoices", field="due_date",
                           start="2026-10-01", end="2026-10-31")

    assert [r["record_key"] for r in invoiced["records"]] == ["VI-2"]
    assert [r["record_key"] for r in due["records"]] == ["VI-1"]


def test_a_date_the_role_does_not_carry_is_refused():
    with pytest.raises(ValueError, match="not a date on"):
        registers.select(PAYOUTS, "processor_payouts", field="settlement_date")


def test_an_ambiguous_role_refuses_to_guess_which_date_is_meant():
    """Payroll carries a period start, a period end and a pay date. Picking one
    silently would produce a defensible-looking register of the wrong thing."""
    with pytest.raises(ValueError, match="several dates"):
        registers.resolve_field("payroll", None)


def test_a_backwards_range_is_refused_rather_than_returning_nothing():
    """An empty result reads as "no transactions", which is a different claim."""
    with pytest.raises(ValueError, match="falls after its end"):
        registers.select(PAYOUTS, "processor_payouts", start="2026-09-30", end="2026-09-01")


def test_a_row_missing_the_date_is_counted_not_silently_dropped():
    """"No payout on that date" and "this row never recorded one" are different
    answers, and only one of them means the books are complete."""
    records = PAYOUTS + [_record("processor_payouts", "PO-4", {"payout_id": "PO-4"})]

    view = registers.select(records, "processor_payouts", start="2026-09-01", end="2026-09-30")

    assert view["records_without_this_date"] == 1
    assert "PO-4" not in [r["record_key"] for r in view["records"]]


def test_an_open_ended_range_is_allowed_at_either_side():
    assert registers.select(PAYOUTS, "processor_payouts", end="2026-09-15")["count"] == 2
    assert registers.select(PAYOUTS, "processor_payouts", start="2026-09-16")["count"] == 1
    assert registers.select(PAYOUTS, "processor_payouts")["count"] == 3


def test_the_export_states_on_its_face_what_it_holds():
    """A spreadsheet that has left the application cannot be asked what it
    meant, so it has to carry that itself."""
    view = registers.select(PAYOUTS, "processor_payouts",
                            start="2026-09-15", end="2026-09-15")
    text = registers.to_csv(view)

    assert "filtered on payout_date" in text
    assert "2026-09-15 to 2026-09-15" in text
    assert "completeness is not verified" in text
    # And every row still points back at the line it came from.
    assert "source_id,source_line" in text
    assert text.count("source-1") == 2


def test_the_export_filename_survives_a_downloads_folder():
    view = registers.select(PAYOUTS, "processor_payouts", start="2026-09-01", end="2026-09-30")
    assert registers.filename(view) == "processor_payouts-by-payout_date-2026-09-01-2026-09-30.csv"


def test_money_reaches_the_spreadsheet_instead_of_an_empty_column():
    """Intake stores money as `<field>_cents`, so writing the declared column
    name straight out left `amount` blank on every row — which in a finance
    export reads as zero rather than as a mapping fault."""
    invoices = [
        _record("vendor_invoices", "VI-1", {"record_id": "VI-1", "invoice_date": "2026-09-08",
                                            "due_date": "2026-09-23", "amount_cents": 120000}),
        _record("vendor_invoices", "VI-2", {"record_id": "VI-2", "invoice_date": "2026-09-18",
                                            "due_date": "2026-09-30", "amount_cents": 50}),
    ]
    view = registers.select(invoices, "vendor_invoices", field="due_date", start="2026-09-01")

    rows = registers.to_csv(view).splitlines()
    header = next(r for r in rows if r.startswith("source_id"))
    body = rows[rows.index(header) + 1:]

    amount = header.split(",").index("amount")
    assert [line.split(",")[amount] for line in body] == ["1200.00", "0.50"]


def test_a_negative_amount_keeps_its_sign_and_its_cents():
    credit = [_record("vendor_invoices", "VI-9", {"record_id": "VI-9", "due_date": "2026-09-10",
                                                  "amount_cents": -148000})]
    view = registers.select(credit, "vendor_invoices", field="due_date")
    assert "-1480.00" in registers.to_csv(view)
