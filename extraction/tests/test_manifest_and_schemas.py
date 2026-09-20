import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from data.manifest_schema import (  # noqa: E402
    DifficultyTag,
    LabelSource,
    Manifest,
    ManifestEntry,
    assert_no_leakage,
    split_by_key,
)
from schemas import grant_agreement, invoice, service_record  # noqa: E402
from schemas.evidence import FieldStatus, extraction_dict_to_raw  # noqa: E402


def _entry(example_id: str, split_key: str, label_source=LabelSource.human_verified) -> ManifestEntry:
    return ManifestEntry(
        example_id=example_id,
        document_path=f"/tmp/{example_id}.pdf",
        document_hash="0" * 64,
        document_type="invoice",
        schema_version=invoice.SCHEMA_VERSION,
        expected_fields={"total": "100.00"},
        label_source=label_source,
        split_key=split_key,
        difficulty_tags=[DifficultyTag.clean],
    )


def test_model_proposed_labels_are_not_admissible():
    assert not _entry("a", "k1", LabelSource.model_proposed).is_admissible_for_training()
    assert _entry("b", "k1", LabelSource.human_verified).is_admissible_for_training()
    assert _entry("c", "k1", LabelSource.imported_ground_truth).is_admissible_for_training()


def test_split_by_key_keeps_groups_intact():
    manifest = Manifest(
        dataset_version="v1",
        entries=[_entry("a", "vendor:X"), _entry("b", "vendor:X"), _entry("c", "vendor:Y")],
    )
    train, holdout = split_by_key(manifest, {"vendor:Y"})
    assert {e.example_id for e in train} == {"a", "b"}
    assert {e.example_id for e in holdout} == {"c"}
    assert_no_leakage(train, holdout)


def test_assert_no_leakage_catches_a_shared_group():
    train = [_entry("a", "vendor:X")]
    holdout = [_entry("b", "vendor:X")]
    with pytest.raises(ValueError, match="leakage"):
        assert_no_leakage(train, holdout)


def test_coverage_by_tag_counts_difficulty_categories():
    manifest = Manifest(dataset_version="v1", entries=[_entry("a", "k"), _entry("b", "k")])
    assert manifest.coverage_by_tag() == {"clean": 2}


def test_status_is_derived_when_the_model_returns_null():
    """Measured NuExtract3 behavior: it returns null for status/quotation on
    every field. Trusting those nulls marked correct extractions unreadable."""
    raw = extraction_dict_to_raw(
        "total", {"status": None, "value": "13473.71", "original_text": "$13473.71", "quotation": None}
    )
    assert raw.status is FieldStatus.present
    assert raw.quotation == "$13473.71"  # falls back to original_text
    assert raw.is_supported()


def test_absent_value_derives_missing_status():
    raw = extraction_dict_to_raw("service_date", {"status": None, "value": None})
    assert raw.status is FieldStatus.missing
    assert raw.is_supported()  # nothing to support


def test_explicit_model_status_is_honored_when_valid():
    raw = extraction_dict_to_raw("total", {"status": "ambiguous", "value": "1.00"})
    assert raw.status is FieldStatus.ambiguous


def test_malformed_entry_does_not_crash():
    raw = extraction_dict_to_raw("total", {"status": "nonsense", "value": "1.00", "locator": "not-a-dict"})
    assert raw.status is FieldStatus.present
    assert raw.locator is None


@pytest.mark.parametrize("module", [invoice, grant_agreement, service_record])
def test_template_requests_only_fields_the_model_actually_fills(module):
    """status/quotation are derived, not requested — measured at 2x the wall
    clock for zero accuracy gain (see schemas/template.py)."""
    scalar = module.template()[next(iter(module.SCALAR_FIELDS))]
    assert set(scalar) == {"value", "original_text"}


def test_locator_can_be_re_enabled_when_a_reviewer_needs_coordinates():
    from schemas.template import build_template

    template = build_template({"total": "verbatim-string"}, include_locator=True)
    assert set(template["total"]) == {"value", "original_text", "locator"}


@pytest.mark.parametrize("module", [invoice, grant_agreement, service_record])
def test_parse_returns_a_raw_extraction_per_declared_field(module):
    parsed = module.parse({})
    assert set(parsed["fields"]) == set(module.SCALAR_FIELDS)
    assert all(r.status is FieldStatus.missing for r in parsed["fields"].values())


def test_invoice_keeps_invoice_service_and_due_dates_distinct():
    """The brief calls date conflation out as a named failure mode."""
    assert {"invoice_date", "service_date", "payment_due_date"} <= set(invoice.SCALAR_FIELDS)


def test_service_record_keeps_pay_and_service_periods_distinct():
    assert {"pay_period_start", "service_period_start"} <= set(service_record.SCALAR_FIELDS)
