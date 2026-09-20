"""The evidence contract every extracted field must carry (spec.md's
ExtractedField, extended with the brief's exact-quotation/locator/status
requirements).

RawExtraction is what the model may claim: a value, the original text it
read, an exact quotation, a locator, and a status. It must never claim a
document ID, document hash, or model version — the model has no reliable way
to know these are correct, and a hallucinated document_id would be worse than
a missing one. ExtractedField wraps a RawExtraction with those attribution
fields filled in by application code, after parsing, from what the caller
actually knows — the same split run_loop.py uses for record_decision's
mechanical fields (when/how) versus its model-supplied judgment fields.

Money is always a decimal string here (e.g. "1234.56"), never a float and
never a value the model computed — this project's existing rule
("deterministic backend code converts it into cents and performs
calculations", api/app/accounting/money.py) applies to extraction the same
way it applies to every agent tool in api/app/agents/.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class FieldStatus(str, Enum):
    present = "present"
    missing = "missing"
    ambiguous = "ambiguous"
    unreadable = "unreadable"


class SourceLocator(BaseModel):
    """Where in the original document a value came from. Populate whichever
    fields apply to the source type — a PDF invoice uses page (+ optionally
    text_span within that page's extracted text); a CSV/table source uses
    row/cell; free text uses text_span alone."""

    model_config = ConfigDict(extra="forbid")

    page: int | None = None
    row: int | None = None
    cell: str | None = None
    text_span: tuple[int, int] | None = None  # (start_char, end_char) within the page/row text


class RawExtraction(BaseModel):
    """What the model itself is allowed to assert for one field. status
    governs how the rest is interpreted: 'missing' means value/original_text/
    quotation/locator should all be None — do not let the model fill them in
    with a guess and still claim 'missing'. 'unreadable' means the model
    could locate where the field should be but could not read it (e.g. a
    scan artifact) — locator should be present even though value is not."""

    model_config = ConfigDict(extra="forbid")

    field_name: str
    status: FieldStatus
    value: str | None = None
    original_text: str | None = None
    quotation: str | None = None
    locator: SourceLocator | None = None

    def is_supported(self) -> bool:
        """A 'present' or 'unreadable' claim without a quotation is an
        unsupported extraction (spec.md §7.5's required metric) — the model
        asserted something it cannot point back to."""
        if self.status in (FieldStatus.missing,):
            return True  # nothing to support
        return bool(self.quotation)


class ExtractedField(BaseModel):
    """RawExtraction plus attribution the application fills in — never the
    model. Constructing one directly from model output without setting these
    is a bug in the caller, not a valid extraction record."""

    model_config = ConfigDict(extra="forbid")

    raw: RawExtraction
    document_id: str
    document_version: str
    document_hash: str
    extraction_method: str  # e.g. "nuextract3-base" or "nuextract3-lora-v3"
    schema_version: str

    @classmethod
    def attach(
        cls,
        raw: RawExtraction,
        *,
        document_id: str,
        document_version: str,
        document_hash: str,
        extraction_method: str,
        schema_version: str,
    ) -> "ExtractedField":
        return cls(
            raw=raw,
            document_id=document_id,
            document_version=document_version,
            document_hash=document_hash,
            extraction_method=extraction_method,
            schema_version=schema_version,
        )


def extraction_dict_to_raw(field_name: str, entry: dict[str, Any]) -> RawExtraction:
    """Parse one field's worth of the model's raw JSON output into a
    RawExtraction, defensively — a model can emit a malformed or incomplete
    entry, and that must not crash the caller.

    status and quotation are DERIVED here, not taken from the model. Measured
    on NuExtract3 against a real invoice (2026-09-19): it populates `value`,
    `original_text` and `locator` faithfully but returns `null` for both
    `status` and `quotation` on every field — they aren't part of its native
    template vocabulary, so asking for them just yields nulls. Trusting the
    model's `status` would have marked eleven correctly-extracted fields
    'unreadable'. If a later model does report status reliably, prefer its
    value over the derivation and re-measure before trusting it.
    """
    value = entry.get("value")
    original_text = entry.get("original_text")

    model_status = entry.get("status")
    if isinstance(model_status, str):
        try:
            status = FieldStatus(model_status)
        except ValueError:
            status = _derive_status(value)
    else:
        status = _derive_status(value)

    locator_dict = entry.get("locator")
    locator = SourceLocator.model_validate(locator_dict) if isinstance(locator_dict, dict) else None

    # The verbatim source text the model read a value from IS the supporting
    # quotation; a separate `quotation` field only adds value if the model
    # actually fills it (NuExtract3 does not).
    quotation = entry.get("quotation") or original_text

    return RawExtraction(
        field_name=field_name,
        status=status,
        value=value,
        original_text=original_text,
        quotation=quotation,
        locator=locator,
    )


def _derive_status(value: Any) -> FieldStatus:
    """No value means the field wasn't found; a value means it was. Neither
    'ambiguous' nor 'unreadable' can be inferred from output alone — those
    need a signal the model doesn't currently give us (an explicit marker or
    a calibrated confidence), so never guess them here."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return FieldStatus.missing
    return FieldStatus.present
