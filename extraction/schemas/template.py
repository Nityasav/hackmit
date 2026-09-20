"""Conversion between a document type's field list and NuExtract3's
template-guided JSON format, and parsing the model's raw output back into
RawExtraction objects per field.

A "template" here is NuExtract3's own input format: a JSON object mapping
field name -> type hint ("verbatim-string", "date-time", "number", or a
nested object/array of the same) — see the model card's own example:
    {"store": "verbatim-string", "total": "number", "items": [{"name": ...}]}

We wrap every field in a small evidence object instead of a bare scalar, so
the model must state status/value/original_text/quotation/locator for each
one — the model card's own examples use bare scalars because a generic demo
doesn't need evidence; this wrapping is this project's schema convention,
not NuExtract3's.

Value type is "verbatim-string" for every field here, including money and
dates — never "number" or "date-time". This project never lets the model
normalize or compute a value it reports (api/app/accounting/money.py's rule,
applied here): we want the exact text as printed, and normalization/
conversion to cents or a parsed date happens in deterministic code that can
be tested and audited, not inside the model's own type coercion.
"""

from __future__ import annotations

from typing import Any

from .evidence import RawExtraction, extraction_dict_to_raw

FieldSchema = dict[str, str]  # field_name -> value type hint (always "verbatim-string" here)


def field_template(include_locator: bool = False, instruction: str | None = None) -> dict[str, Any]:
    """Only `value` and `original_text` are requested by default.

    Measured on NuExtract3 (Apple M5 / MPS, same invoice, greedy decoding):

        requested fields              gen tokens   time    accuracy
        value+original+status+quote+locator  1284   192.7s   5/5
        value+original_text                   574    91.3s   5/5

    `status` and `quotation` came back null on every field in every run — they
    aren't part of the model's native template vocabulary, so asking for them
    bought nothing and cost half the wall clock. Both are derived in
    evidence.py instead (status from whether a value came back; quotation
    from original_text, which the model does fill verbatim).

    `locator` is off by default for the same reason: citation checking in
    scripts/evaluate.py verifies the quotation *text* against the page text,
    not a coordinate, and pages are rendered one at a time so `page` is
    already known. Turn it on if a reviewer UI needs row/cell coordinates to
    jump to — and re-measure, because it is not free.
    """
    # MEASURED: prose instructions in the type-hint slot do NOT steer this
    # model. Putting "Legal entity name only, exclude honorifics such as
    # Esq." here changed nothing across 6 invoices — it still returned
    # "Marcus Avila, Esq." every time. NuExtract3's template vocabulary is
    # closed ("verbatim-string" / "date-time" / "number"); the slot is a type
    # hint, not a prompt channel. Per-field normalization has to happen in
    # schemas/normalize.py after extraction instead.
    template: dict[str, Any] = {
        "value": "verbatim-string",
        "original_text": "verbatim-string",
    }
    if include_locator:
        template["locator"] = {"page": "integer", "row": "integer", "cell": "verbatim-string"}
    return template


def build_template(
    scalar_fields: FieldSchema,
    list_fields: dict[str, FieldSchema] | None = None,
    include_locator: bool = False,
    instructions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """scalar_fields: header-level fields (e.g. invoice number, vendor).
    list_fields: name -> item field schema, for repeating structures (e.g.
    invoice line items, grant amendments).
    instructions: field name -> how that field should be normalized, for the
    few fields where the printed form and the wanted form differ."""
    instructions = instructions or {}
    template: dict[str, Any] = {
        name: field_template(include_locator, instructions.get(name)) for name in scalar_fields
    }
    for list_name, item_fields in (list_fields or {}).items():
        template[list_name] = [
            {name: field_template(include_locator, instructions.get(name)) for name in item_fields}
        ]
    return template


def parse_scalar_fields(scalar_fields: FieldSchema, raw_output: dict[str, Any]) -> dict[str, RawExtraction]:
    return {
        name: extraction_dict_to_raw(name, raw_output.get(name) or {})
        for name in scalar_fields
    }


def parse_list_field(
    item_fields: FieldSchema, raw_items: list[dict[str, Any]] | None
) -> list[dict[str, RawExtraction]]:
    parsed: list[dict[str, RawExtraction]] = []
    for item in raw_items or []:
        parsed.append({name: extraction_dict_to_raw(name, item.get(name) or {}) for name in item_fields})
    return parsed
