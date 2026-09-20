"""Deterministic payroll calculations.

These assert arithmetic and reperformability, not agent reasoning. Every value
here must be reproducible by the Internal Auditor through the same functions.
"""

from app.accounting.payroll import calculations

WS_PAYROLL = {
    "role": "payroll", "record_key": "PAY-1", "source_id": "src-payroll", "locator": 2,
    "payload": {"record_id": "PAY-1", "employee_id": "EMP-01", "service_start": "2026-09-01",
                "service_end": "2026-09-30", "pay_date": "2026-09-15", "gross_cents": 1_000_000,
                "deductions_cents": 0, "net_cents": 1_000_000, "employer_cost_cents": 0,
                "award_id": "GRANT-1", "award_amount_cents": 1_000_000},
}
WS_GRANT = {
    "role": "grants", "record_key": "GRANT-1", "source_id": "src-grants", "locator": 2,
    "payload": {"award_id": "GRANT-1", "name": "Student support", "ceiling_cents": 5_000_000,
                "valid_from": "2026-09-01", "valid_to": "2027-06-30"},
}
WS_CHART = {
    "role": "chart", "record_key": "5000", "source_id": "src-chart", "locator": 4,
    "payload": {"account": "5000", "name": "Salary expense", "type": "expense",
                "report_mapping": "payroll", "effective_from": "2026-01-01"},
}
WS_LEDGER = {
    "role": "ledger", "record_key": "PAY-1/1", "source_id": "src-ledger", "locator": 2,
    "payload": {"entry_id": "PAY-1", "line_id": "1", "date": "2026-09-15", "account": "5000",
                "debit_cents": 1_000_000, "credit_cents": 0},
}


def by_id(records, service_present=False):
    return {c.id: c for c in calculations(records, service_present)}


def test_no_payroll_records_publish_no_amounts():
    assert calculations([WS_GRANT, WS_CHART], service_present=True) == []


def test_gross_to_net_and_total_expense_use_employer_cost():
    payroll = {**WS_PAYROLL, "payload": {**WS_PAYROLL["payload"], "gross_cents": 1_000_000,
                                         "deductions_cents": 250_000, "net_cents": 750_000,
                                         "employer_cost_cents": 180_000}}
    results = by_id([payroll])
    tie = results["payroll-gross-to-net"]
    assert tie.amount_cents == 0 and tie.category == "none" and tie.cash_delta_cents == 0
    # Payroll expense is gross plus employer cost, never net pay (ACCOUNTING_CONTROLS §6).
    assert results["payroll-total-expense"].amount_cents == 1_180_000


def test_gross_to_net_residual_is_reported_as_exposure():
    broken = {**WS_PAYROLL, "payload": {**WS_PAYROLL["payload"], "gross_cents": 1_000_000,
                                        "deductions_cents": 250_000, "net_cents": 700_000}}
    tie = by_id([broken])["payroll-gross-to-net"]
    assert tie.amount_cents == 50_000 and tie.category == "exposure"


def test_allocation_without_any_service_record_is_a_reclassification_candidate():
    unsupported = by_id([WS_PAYROLL, WS_GRANT], service_present=False)["payroll-unsupported-by-service-evidence"]
    assert unsupported.amount_cents == 1_000_000
    assert unsupported.category == "reclassification"
    # A fund reclassification never moves cash.
    assert unsupported.cash_delta_cents == 0


def test_service_evidence_present_stops_the_engine_asserting_an_unsupported_amount():
    supported = by_id([WS_PAYROLL, WS_GRANT], service_present=True)["payroll-unsupported-by-service-evidence"]
    assert supported.amount_cents == 0 and supported.category == "none"
    # The engine does not read a percentage out of prose; that split needs a structured record.
    assert "does not judge" in supported.basis


def test_ceiling_excess_is_measured_per_award():
    over = {**WS_PAYROLL, "payload": {**WS_PAYROLL["payload"], "award_amount_cents": 6_000_000,
                                      "gross_cents": 6_000_000, "net_cents": 6_000_000}}
    results = by_id([over, WS_GRANT])
    assert results["payroll-award-ceiling-excess"].amount_cents == 1_000_000
    assert results["payroll-award-ceiling-excess"].category == "exposure"
    assert by_id([WS_PAYROLL, WS_GRANT])["payroll-award-ceiling-excess"].amount_cents == 0


def test_service_period_outside_the_award_window_is_flagged_in_full():
    early = {**WS_PAYROLL, "payload": {**WS_PAYROLL["payload"], "service_start": "2026-08-01"}}
    outside = by_id([early, WS_GRANT])["payroll-outside-award-window"]
    assert outside.amount_cents == 1_000_000 and outside.category == "reclassification"
    assert by_id([WS_PAYROLL, WS_GRANT])["payroll-outside-award-window"].amount_cents == 0


def test_allocation_to_an_unsupplied_award_is_an_exposure():
    assert by_id([WS_PAYROLL])["payroll-unknown-award"].amount_cents == 1_000_000
    assert by_id([WS_PAYROLL, WS_GRANT])["payroll-unknown-award"].amount_cents == 0


def test_ledger_tie_uses_payroll_mapped_accounts_only():
    results = by_id([WS_PAYROLL, WS_GRANT, WS_CHART, WS_LEDGER])
    assert results["payroll-ledger-tie"].amount_cents == 0
    other_account = {**WS_LEDGER, "payload": {**WS_LEDGER["payload"], "account": "1000"}}
    unmatched = by_id([WS_PAYROLL, WS_GRANT, WS_CHART, other_account])["payroll-ledger-tie"]
    assert unmatched.amount_cents == 1_000_000 and unmatched.category == "exposure"


def test_ledger_tie_is_withheld_without_a_chart_or_ledger():
    assert "payroll-ledger-tie" not in by_id([WS_PAYROLL, WS_GRANT])
    assert "payroll-award-ceiling-excess" not in by_id([WS_PAYROLL])


def test_every_calculation_declares_the_sources_it_rests_on_and_is_stable():
    records = [WS_PAYROLL, WS_GRANT, WS_CHART, WS_LEDGER]
    first = calculations(records, service_present=False)
    assert first == calculations(list(reversed(records)), service_present=False)
    assert [c.id for c in first] == sorted(c.id for c in first)
    for result in first:
        assert result.source_ids and set(result.source_ids) <= {"src-payroll", "src-grants", "src-chart", "src-ledger"}
        assert result.cash_delta_cents == 0
