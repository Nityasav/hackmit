from decimal import Decimal
from pathlib import Path

from app.agents.ar_reconciliation import (
    CLASSIFY_DOCUMENTS_SPEC,
    DocumentClassification,
    bind_classify_documents,
    reduce_to_customer_totals,
    write_submission_csv,
)


def test_classify_documents_appends_to_the_ledger():
    ledger: list[DocumentClassification] = []
    classify = bind_classify_documents(ledger)

    result = classify(
        classifications=[
            {
                "file_path": "invoices/INV-1.pdf",
                "document_type": "valid_invoice",
                "reason": "clean invoice",
                "customer_id": "C001",
                "amount_usd": "100.00",
            }
        ]
    )

    assert result["recorded"] == 1
    assert ledger[0].customer_id == "C001"
    assert ledger[0].amount_usd == Decimal("100.00")


def test_classify_documents_rejects_unknown_document_type():
    ledger: list[DocumentClassification] = []
    classify = bind_classify_documents(ledger)

    result = classify(
        classifications=[{"file_path": "invoices/INV-1.pdf", "document_type": "not_a_real_type", "reason": "x"}]
    )

    assert result["recorded"] == 0
    assert ledger == []
    assert "skipped invalid entry" in result["errors"][0]


def test_classify_documents_rejects_invalid_amount_string():
    ledger: list[DocumentClassification] = []
    classify = bind_classify_documents(ledger)

    result = classify(
        classifications=[
            {
                "file_path": "invoices/INV-1.pdf",
                "document_type": "valid_invoice",
                "reason": "x",
                "customer_id": "C001",
                "amount_usd": "not a number",
            }
        ]
    )

    assert result["recorded"] == 0
    assert "invalid amount_usd" in result["errors"][0]


def test_classify_documents_absorbs_injected_workspace_kwarg():
    """ToolGateway.call always injects workspace= into every dispatched call."""
    ledger: list[DocumentClassification] = []
    classify = bind_classify_documents(ledger)
    result = classify(classifications=[], workspace="/some/path")
    assert result["recorded"] == 0


def test_reduce_sums_valid_invoices_per_customer():
    ledger = [
        DocumentClassification("invoices/a.pdf", "valid_invoice", "r", "C001", Decimal("100.00")),
        DocumentClassification("invoices/b.pdf", "valid_invoice", "r", "C001", Decimal("50.00")),
        DocumentClassification("invoices/c.pdf", "valid_invoice", "r", "C002", Decimal("25.00")),
    ]
    totals = reduce_to_customer_totals(ledger)
    assert totals == {"C001": Decimal("150.00"), "C002": Decimal("25.00")}


def test_reduce_subtracts_credit_memos():
    ledger = [
        DocumentClassification("invoices/a.pdf", "valid_invoice", "r", "C001", Decimal("100.00")),
        DocumentClassification("invoices/cm.pdf", "credit_memo", "r", "C001", Decimal("15.00")),
    ]
    totals = reduce_to_customer_totals(ledger)
    assert totals == {"C001": Decimal("85.00")}


def test_reduce_subtracts_credit_memos_even_when_the_model_already_signed_them_negative():
    """Regression: a live run had the model transcribe a credit memo's total
    exactly as printed on the document — negative, matching the benchmark's
    own answer key convention — and reduce_to_customer_totals double-negated
    it (treating -15.00 as a -(-15.00) = +15.00 addition instead of a $15
    reduction). Correct regardless of which sign convention the model used."""
    ledger = [
        DocumentClassification("invoices/a.pdf", "valid_invoice", "r", "C001", Decimal("100.00")),
        DocumentClassification("invoices/cm.pdf", "credit_memo", "r", "C001", Decimal("-15.00")),
    ]
    totals = reduce_to_customer_totals(ledger)
    assert totals == {"C001": Decimal("85.00")}


def test_reduce_excludes_non_spend_document_types():
    ledger = [
        DocumentClassification("invoices/void.pdf", "void", "r", "C001", Decimal("999.00")),
        DocumentClassification("invoices/dup.pdf", "duplicate", "r", "C001", Decimal("999.00")),
        DocumentClassification("invoices/super.pdf", "superseded", "r", "C001", Decimal("999.00")),
        DocumentClassification("invoices/stmt.pdf", "statement", "r", "C001", Decimal("999.00")),
        DocumentClassification("bank_exports/deposits.csv", "not_applicable", "r", "C001", Decimal("500.00")),
    ]
    totals = reduce_to_customer_totals(ledger)
    assert totals == {}


def test_reduce_ignores_entries_missing_customer_or_amount():
    ledger = [
        DocumentClassification("invoices/a.pdf", "valid_invoice", "r", None, Decimal("100.00")),
        DocumentClassification("invoices/b.pdf", "valid_invoice", "r", "C001", None),
    ]
    assert reduce_to_customer_totals(ledger) == {}


def test_reduce_uses_the_latest_classification_for_a_reclassified_file():
    """A model that reads a file, classifies it, then corrects itself after
    re-reading should not be charged twice for the same document."""
    ledger = [
        DocumentClassification("invoices/a.pdf", "valid_invoice", "first pass", "C001", Decimal("100.00")),
        DocumentClassification("invoices/a.pdf", "duplicate", "actually a duplicate scan", "C001", Decimal("100.00")),
    ]
    assert reduce_to_customer_totals(ledger) == {}


def test_reduce_handles_many_small_amounts_without_float_drift():
    ledger = [
        DocumentClassification(f"invoices/{i}.pdf", "valid_invoice", "r", "C001", Decimal("0.10"))
        for i in range(30)
    ]
    totals = reduce_to_customer_totals(ledger)
    assert totals["C001"] == Decimal("3.00")


def test_write_submission_csv_format(tmp_path: Path):
    totals = {"C002": Decimal("25.5"), "C001": Decimal("150")}
    output = write_submission_csv(totals, str(tmp_path / "out" / "submission.csv"))

    content = output.read_text(encoding="utf-8")
    lines = content.strip().splitlines()
    assert lines[0] == "customer_id,net_spend_usd"
    # Sorted by customer_id, and every amount quantized to 2 decimals.
    assert lines[1] == "C001,150.00"
    assert lines[2] == "C002,25.50"


def test_classify_documents_spec_enum_matches_reducer_semantics():
    enum_values = set(CLASSIFY_DOCUMENTS_SPEC["parameters"]["properties"]["classifications"]["items"]["properties"][
        "document_type"
    ]["enum"])
    assert enum_values == {
        "valid_invoice", "credit_memo", "void", "superseded", "duplicate", "statement", "not_applicable",
    }
