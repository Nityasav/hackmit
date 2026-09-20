"""Invoice extraction target schema (spec.md's Invoice/InvoiceLine, brief §1).

Invoice date, service date, and payment/due date are kept as three distinct
fields on purpose — the brief calls this out explicitly as a common
extraction failure mode (a model conflating "the date on the invoice" with
"when the service happened" with "when it's due"), and this project's own AP
agent (api/app/agents/ap_records.py) already treats invoice_date and
service_start/service_end as separate facts for exactly this reason.
"""

from __future__ import annotations

from typing import Any

from .evidence import RawExtraction
from .normalize import normalize_fields
from .template import FieldSchema, build_template, parse_list_field, parse_scalar_fields

SCALAR_FIELDS: FieldSchema = {
    "vendor_name": "verbatim-string",
    "invoice_number": "verbatim-string",
    "invoice_date": "verbatim-string",
    "service_date": "verbatim-string",
    "payment_due_date": "verbatim-string",
    "currency": "verbatim-string",
    "subtotal": "verbatim-string",
    "tax": "verbatim-string",
    "total": "verbatim-string",
    "purchase_order_reference": "verbatim-string",
    "receipt_reference": "verbatim-string",
}

LINE_ITEM_FIELDS: FieldSchema = {
    "description": "verbatim-string",
    "quantity": "verbatim-string",
    "unit_price": "verbatim-string",
    "amount": "verbatim-string",
}

SCHEMA_VERSION = "invoice-v1"


def template() -> dict[str, Any]:
    return build_template(SCALAR_FIELDS, {"line_items": LINE_ITEM_FIELDS})


def parse(raw_output: dict[str, Any]) -> dict[str, Any]:
    """Returns {"fields": {name: RawExtraction}, "line_items": [{name: RawExtraction}, ...]}.
    Callers wrap each RawExtraction into an ExtractedField with document
    attribution (see schemas/evidence.py) before this leaves the extraction
    layer — never pass a bare RawExtraction into accounting code."""
    return {
        "fields": normalize_fields(parse_scalar_fields(SCALAR_FIELDS, raw_output)),
        "line_items": parse_list_field(LINE_ITEM_FIELDS, raw_output.get("line_items")),
    }
