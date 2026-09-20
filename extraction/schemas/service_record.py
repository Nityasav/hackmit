"""Payroll / service record extraction target schema (spec.md's PayrollLine,
brief §1).

Pay period and service period are separate fields on purpose. This project's
own planted-issue catalog turns on exactly that distinction — a charge whose
*service* date falls outside an award window is an exception even though its
*pay* date falls inside it — so collapsing them into one "period" field would
destroy the signal the Grants and Payroll agents need.

Award allocations are a list: one payroll line can be split across several
awards/funds, and the split percentages are the thing a reviewer most often
has to check against a service record.
"""

from __future__ import annotations

from typing import Any

from .normalize import normalize_fields
from .template import FieldSchema, build_template, parse_list_field, parse_scalar_fields

SCALAR_FIELDS: FieldSchema = {
    "employee_identifier": "verbatim-string",
    "pay_period_start": "verbatim-string",
    "pay_period_end": "verbatim-string",
    "service_period_start": "verbatim-string",
    "service_period_end": "verbatim-string",
    "currency": "verbatim-string",
    "gross_pay": "verbatim-string",
    "total_deductions": "verbatim-string",
    "net_pay": "verbatim-string",
    "employer_costs": "verbatim-string",
    "documented_hours": "verbatim-string",
    "documented_services": "verbatim-string",
}

ALLOCATION_FIELDS: FieldSchema = {
    "award_or_fund": "verbatim-string",
    "allocation_percentage": "verbatim-string",
    "allocation_amount": "verbatim-string",
    "supporting_reference": "verbatim-string",
}

SCHEMA_VERSION = "service-record-v1"


def template() -> dict[str, Any]:
    return build_template(SCALAR_FIELDS, {"award_allocations": ALLOCATION_FIELDS})


def parse(raw_output: dict[str, Any]) -> dict[str, Any]:
    return {
        "fields": normalize_fields(parse_scalar_fields(SCALAR_FIELDS, raw_output)),
        "award_allocations": parse_list_field(ALLOCATION_FIELDS, raw_output.get("award_allocations")),
    }
