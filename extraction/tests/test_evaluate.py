import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decimal import Decimal  # noqa: E402

from scripts.evaluate import (  # noqa: E402
    ExampleResult,
    Outcome,
    aggregate,
    citation_resolves,
    normalize_date,
    normalize_money,
    score_fields,
    values_match,
)


def test_normalize_money_strips_symbols_and_separators():
    assert normalize_money("$12,592.25") == Decimal("12592.25")
    assert normalize_money(" 881.46 ") == Decimal("881.46")


def test_normalize_money_handles_accounting_negatives():
    assert normalize_money("(1,480.00)") == Decimal("-1480.00")
    assert normalize_money("-1480.00") == Decimal("-1480.00")


def test_normalize_money_rejects_non_numeric():
    assert normalize_money("n/a") is None
    assert normalize_money("") is None


def test_money_comparison_ignores_formatting_but_not_value():
    assert values_match("total", "13473.71", "$13,473.71")
    assert not values_match("total", "13473.71", "13473.17")


def test_normalize_date_recognizes_common_formats():
    assert normalize_date("2025-05-01") == "2025-05-01"
    assert normalize_date("5/1/2025") == "2025-05-01"
    assert normalize_date("2025/5/1") == "2025-05-01"


def test_month_name_dates_normalize_because_order_is_unambiguous():
    """The APEX contract-attorney invoices print "March 20, 2024"; without
    this a model correctly answering ISO would be scored wrong."""
    assert normalize_date("March 20, 2024") == "2024-03-20"
    assert normalize_date("20 March 2024") == "2024-03-20"
    assert normalize_date("Sept 3, 2024") == "2024-09-03"
    assert values_match("invoice_date", "March 20, 2024", "2024-03-20")


def test_ambiguous_numeric_date_format_is_still_not_coerced():
    """Guessing day/month order would silently score a wrong date correct."""
    assert normalize_date("20.03.2024") is None
    assert values_match("invoice_date", "20.03.2024", "20.03.2024")
    assert not values_match("invoice_date", "20.03.2024", "2024-03-20")


def test_currency_symbol_matches_iso_code():
    """The APEX run returned '$' (what the invoice prints, which is what a
    verbatim-string field asks for) against 'USD' labels — 21 of 27 apparent
    failures from one unstated convention."""
    assert values_match("currency", "USD", "$")
    assert values_match("currency", "$", "US$")
    assert values_match("currency", "EUR", "€")
    assert not values_match("currency", "USD", "€")


def test_currency_normalizer_does_not_leak_into_other_fields():
    """'$' and 'USD' are the same currency but not the same vendor name."""
    assert not values_match("vendor_name", "USD", "$")


def test_id_comparison_ignores_case_and_whitespace():
    assert values_match("invoice_number", "INV-2025-1001", " inv-2025-1001 ")
    assert not values_match("invoice_number", "INV-2025-1001", "INV-2025-1002")


def test_outcome_taxonomy_covers_all_five_cases():
    expected = {
        "total": "100.00",        # correct
        "tax": "10.00",           # wrong value
        "subtotal": "90.00",      # missed
        "service_date": None,     # over-extracted
        "receipt_reference": None,  # correct abstention
    }
    predicted = {
        "total": {"value": "100.00", "quotation": "Total $100.00"},
        "tax": {"value": "11.00", "quotation": "Tax $11.00"},
        "subtotal": {"value": None, "quotation": None},
        "service_date": {"value": "2025-01-01", "quotation": None},
        "receipt_reference": {"value": None, "quotation": None},
    }
    outcomes = {r.field_name: r.outcome for r in score_fields(expected, predicted)}
    assert outcomes["total"] is Outcome.correct
    assert outcomes["tax"] is Outcome.wrong_value
    assert outcomes["subtotal"] is Outcome.missed
    assert outcomes["service_date"] is Outcome.over_extracted
    assert outcomes["receipt_reference"] is Outcome.correct_abstention


def test_citation_resolves_against_real_page_text():
    page = "Invoice INV-2025-1001\nSubtotal $12592.25\nTotal $13473.71"
    assert citation_resolves("Subtotal $12592.25", page) is True
    assert citation_resolves("Subtotal $99999.99", page) is False
    assert citation_resolves(None, page) is None


def test_citation_check_is_whitespace_insensitive():
    assert citation_resolves("Total   $13473.71", "Total $13473.71") is True


def test_fabricated_citation_is_caught_even_when_value_is_right():
    """The property that makes an extraction reviewable: a right answer with
    a made-up quotation must not pass silently."""
    page = "Total $13473.71"
    results = score_fields(
        {"total": "13473.71"},
        {"total": {"value": "13473.71", "quotation": "Grand Total: 13473.71 USD"}},
        page,
    )
    assert results[0].outcome is Outcome.correct
    assert results[0].citation_ok is False


def test_aggregate_precision_recall_penalize_wrong_values_twice():
    results = [
        ExampleResult(
            example_id="e1",
            split_key="k",
            valid_json=True,
            fields=score_fields(
                {"total": "100.00", "tax": "10.00"},
                {
                    "total": {"value": "100.00", "quotation": "Total $100.00"},
                    "tax": {"value": "99.00", "quotation": "Tax $99.00"},
                },
            ),
        )
    ]
    summary = aggregate(results)
    assert summary["precision"] == 0.5  # 1 correct of 2 predicted
    assert summary["recall"] == 0.5     # 1 correct of 2 labeled present


def test_aggregate_reports_abstention_quality_and_unsupported_rate():
    results = [
        ExampleResult(
            example_id="e1",
            split_key="k",
            valid_json=True,
            fields=score_fields(
                {"service_date": None, "receipt_reference": None, "total": "5.00"},
                {
                    "service_date": {"value": "2025-01-01", "quotation": None},  # over-extracted, unsupported
                    "receipt_reference": {"value": None, "quotation": None},     # correct abstention
                    "total": {"value": "5.00", "quotation": "Total $5.00"},
                },
            ),
        )
    ]
    summary = aggregate(results)
    assert summary["abstention_quality"] == 0.5   # 1 correct abstention of 2 opportunities
    assert summary["unsupported_extraction_rate"] == 0.5  # 1 of 2 claims had no quotation


def test_invalid_json_counts_against_valid_json_rate():
    results = [
        ExampleResult(example_id="a", split_key="k", valid_json=True, fields=[]),
        ExampleResult(example_id="b", split_key="k", valid_json=False, fields=[]),
    ]
    assert aggregate(results)["valid_json_rate"] == 0.5
