"""Grant agreement extraction target schema (spec.md's Award, brief §1).

Amendments are their own list, not folded into the header fields — a grant
agreement's ceiling/dates/terms can change over its life, and this project's
own duplicate-precedent lesson (schooltrace's playbook-retirement example:
a contract amendment invalidates an old allocation precedent) applies to
extraction too: an amendment must be a distinct, dated fact, not silently
overwrite the original terms in the same field.
"""

from __future__ import annotations

from typing import Any

from .normalize import normalize_fields
from .template import FieldSchema, build_template, parse_list_field, parse_scalar_fields

SCALAR_FIELDS: FieldSchema = {
    "award_id": "verbatim-string",
    "funder": "verbatim-string",
    "ceiling_amount": "verbatim-string",
    "currency": "verbatim-string",
    "eligible_start_date": "verbatim-string",
    "eligible_end_date": "verbatim-string",
    "allowed_expenses": "verbatim-string",
    "prohibited_expenses": "verbatim-string",
    "reporting_obligations": "verbatim-string",
}

AMENDMENT_FIELDS: FieldSchema = {
    "amendment_date": "verbatim-string",
    "amendment_description": "verbatim-string",
    "change_to_ceiling": "verbatim-string",
    "change_to_eligible_dates": "verbatim-string",
}

SCHEMA_VERSION = "grant-agreement-v1"


def template() -> dict[str, Any]:
    return build_template(SCALAR_FIELDS, {"amendments": AMENDMENT_FIELDS})


def parse(raw_output: dict[str, Any]) -> dict[str, Any]:
    return {
        "fields": normalize_fields(parse_scalar_fields(SCALAR_FIELDS, raw_output)),
        "amendments": parse_list_field(AMENDMENT_FIELDS, raw_output.get("amendments")),
    }
