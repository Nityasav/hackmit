"""AP and award-level calculations: exact cents, and nothing asserted without records.

Before these existed the auditor rejected every substantiated AP or grants claim,
because a substantiated claim with no deterministic calculation has nothing to
reperform. That is why five-agent runs accepted nothing from those two agents.
"""

from app.accounting import ap, grants


def _invoice(record_id, vendor, number, amount_cents, *, po=None, receipt=None,
             award=None, date="2026-09-10", source="src-inv"):
    payload = {"record_id": record_id, "vendor_id": vendor, "invoice_number": number,
               "amount_cents": amount_cents, "service_date": date}
    if po:
        payload["po_id"] = po
    if receipt:
        payload["receipt_id"] = receipt
    if award:
        payload["award_id"] = award
    return {"role": "invoice", "record_key": record_id, "payload": payload,
            "source_id": source, "locator": 1}


def _payroll(record_id, award, award_cents, *, start="2026-09-01", end="2026-09-30", source="src-pay"):
    return {"role": "payroll", "record_key": record_id, "source_id": source, "locator": 1,
            "payload": {"record_id": record_id, "award_id": award, "award_amount_cents": award_cents,
                        "gross_cents": award_cents, "employer_cost_cents": 0,
                        "service_start": start, "service_end": end}}


def _grant(award, ceiling_cents, *, valid_from="2026-09-01", valid_to="2027-06-30", source="src-gr"):
    return {"role": "grants", "record_key": award, "source_id": source, "locator": 1,
            "payload": {"award_id": award, "ceiling_cents": ceiling_cents,
                        "valid_from": valid_from, "valid_to": valid_to}}


def _by_id(results):
    return {c.id: c for c in results}


# --------------------------------------------------------------------------- #
# AP
# --------------------------------------------------------------------------- #

def test_no_invoices_means_no_ap_amount_may_be_asserted():
    assert ap.calculations([_payroll("PAY-1", "GRANT-1", 1000)]) == []


def test_a_repeated_invoice_number_is_priced_beyond_the_first_occurrence():
    records = [_invoice("INV-1", "V-1", "A-100", 500_00),
               _invoice("INV-2", "V-1", "A-100", 500_00),
               _invoice("INV-3", "V-1", "A-101", 250_00)]
    duplicate = _by_id(ap.calculations(records))["ap-duplicate-exposure"]
    assert duplicate.amount_cents == 500_00, "the first occurrence is the original"
    assert duplicate.category == "exposure"
    assert "occur more than once" in duplicate.basis


def test_the_same_number_from_a_different_vendor_is_not_a_duplicate():
    records = [_invoice("INV-1", "V-1", "A-100", 500_00),
               _invoice("INV-2", "V-2", "A-100", 500_00)]
    assert _by_id(ap.calculations(records))["ap-duplicate-exposure"].amount_cents == 0


def test_three_repeats_price_both_extra_occurrences():
    records = [_invoice(f"INV-{i}", "V-1", "A-100", 100_00) for i in range(1, 4)]
    assert _by_id(ap.calculations(records))["ap-duplicate-exposure"].amount_cents == 200_00


def test_missing_support_references_are_priced_separately():
    records = [_invoice("INV-1", "V-1", "A-1", 300_00, po="PO-1", receipt="GR-1"),
               _invoice("INV-2", "V-1", "A-2", 700_00)]
    results = _by_id(ap.calculations(records))
    assert results["ap-without-purchase-order"].amount_cents == 700_00
    assert results["ap-without-goods-receipt"].amount_cents == 700_00
    assert results["ap-invoiced-total"].amount_cents == 1_000_00
    # A missing reference is an indicator, and the basis has to say so.
    assert "not proof" in results["ap-without-purchase-order"].basis


def test_fully_supported_invoices_report_zero_rather_than_an_exposure():
    records = [_invoice("INV-1", "V-1", "A-1", 300_00, po="PO-1", receipt="GR-1")]
    results = _by_id(ap.calculations(records))
    assert results["ap-without-purchase-order"].category == "none"
    assert results["ap-without-goods-receipt"].amount_cents == 0


def test_every_ap_calculation_names_the_sources_behind_it():
    records = [_invoice("INV-1", "V-1", "A-1", 100_00, source="src-a"),
               _invoice("INV-2", "V-2", "A-2", 100_00, source="src-b")]
    for calculation in ap.calculations(records):
        assert calculation.source_ids == ("src-a", "src-b")


# --------------------------------------------------------------------------- #
# Awards
# --------------------------------------------------------------------------- #

def test_nothing_charged_to_an_award_means_no_award_amount():
    assert grants.calculations([_invoice("INV-1", "V-1", "A-1", 100_00)]) == []


def test_an_award_ceiling_counts_payroll_and_invoices_together():
    """The point of the module: a payroll-only test understates the award."""
    records = [_grant("GRANT-1", 1_000_00),
               _payroll("PAY-1", "GRANT-1", 600_00),
               _invoice("INV-1", "V-1", "A-1", 700_00, award="GRANT-1")]
    results = _by_id(grants.calculations(records))
    assert results["grants-award-charges"].amount_cents == 1_300_00
    assert results["grants-combined-ceiling-excess"].amount_cents == 300_00
    assert results["grants-combined-ceiling-excess"].category == "exposure"


def test_an_award_within_its_ceiling_reports_no_excess():
    records = [_grant("GRANT-1", 1_000_00), _payroll("PAY-1", "GRANT-1", 400_00)]
    excess = _by_id(grants.calculations(records))["grants-combined-ceiling-excess"]
    assert excess.amount_cents == 0 and excess.category == "none"


def test_a_charge_outside_the_award_window_is_priced():
    records = [_grant("GRANT-1", 10_000_00, valid_from="2026-10-01", valid_to="2027-06-30"),
               _invoice("INV-1", "V-1", "A-1", 250_00, award="GRANT-1", date="2026-09-10")]
    outside = _by_id(grants.calculations(records))["grants-combined-outside-window"]
    assert outside.amount_cents == 250_00 and outside.category == "exposure"


def test_a_charge_inside_the_window_is_not_flagged():
    records = [_grant("GRANT-1", 10_000_00),
               _invoice("INV-1", "V-1", "A-1", 250_00, award="GRANT-1", date="2026-09-10")]
    assert _by_id(grants.calculations(records))["grants-combined-outside-window"].amount_cents == 0


def test_a_charge_to_an_award_outside_the_register_is_priced():
    records = [_grant("GRANT-1", 10_000_00),
               _invoice("INV-1", "V-1", "A-1", 900_00, award="GRANT-9")]
    unknown = _by_id(grants.calculations(records))["grants-charges-to-unknown-award"]
    assert unknown.amount_cents == 900_00
    assert "GRANT-9" in unknown.basis


def test_award_tests_are_withheld_when_no_register_is_committed():
    """Without ceilings or windows there is nothing to test a charge against."""
    published = _by_id(grants.calculations([_payroll("PAY-1", "GRANT-1", 600_00)]))
    assert "grants-combined-ceiling-excess" not in published
    assert published["grants-charges-to-unknown-award"].amount_cents == 600_00


def test_award_calculations_are_exact_cents_not_floats():
    records = [_grant("GRANT-1", 1_00), _payroll("PAY-1", "GRANT-1", 33), _payroll("PAY-2", "GRANT-1", 34),
               _payroll("PAY-3", "GRANT-1", 34)]
    total = _by_id(grants.calculations(records))["grants-award-charges"].amount_cents
    assert total == 101 and isinstance(total, int)
