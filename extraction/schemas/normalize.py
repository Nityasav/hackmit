"""Deterministic post-processing of extracted values.

Some fields need a canonical form that differs from what the page prints.
Vendor matching is the motivating case: an invoice says "Marcus Avila, Esq."
but the vendor master says "Marcus Avila", and a downstream match on the
printed string fails.

Two things this deliberately does NOT do:

  * It does not live in scripts/evaluate.py. Normalizing only in the scorer
    would make the metric read 1.0 while the extraction layer still handed
    accounting a value it can't match on — a fixed number hiding a live bug.
  * It does not touch `original_text`. That stays exactly as printed, because
    it is the quotation that has to resolve against the page for citation
    checking. `value` becomes canonical; `original_text` stays evidence.

Why deterministic code and not the model: prose instructions in NuExtract3's
template were measured to have no effect (see schemas/template.py) — its type
slot is a closed vocabulary, not a prompt. Stripping a suffix is exactly the
kind of rule that belongs in testable code anyway, not in model weights.
"""

from __future__ import annotations

import re

from .evidence import RawExtraction

# Credential/honorific suffixes to drop. Business entity suffixes (LLC, PLLC,
# Inc., LLP, PC, Ltd) are deliberately NOT here — they are part of the
# registered legal name and dropping them would break matching in the other
# direction.
_HONORIFICS = {
    "esq", "esquire", "jr", "sr", "ii", "iii", "iv",
    "phd", "ph d", "md", "cpa", "cfa", "jd", "mba", "rn", "dds",
}

_HONORIFIC_TAIL = re.compile(
    r"[,\s]+(" + "|".join(re.escape(h) for h in sorted(_HONORIFICS, key=len, reverse=True)) + r")\.?\s*$",
    re.IGNORECASE,
)


def strip_honorifics(name: str) -> str:
    """Remove trailing credential suffixes, repeatedly ("Jane Doe, MD, PhD")."""
    cleaned = name.strip()
    while True:
        stripped = _HONORIFIC_TAIL.sub("", cleaned).strip().rstrip(",").strip()
        if stripped == cleaned:
            return cleaned
        cleaned = stripped


# field name -> normalizer applied to `value` only.
NORMALIZERS = {
    "vendor_name": strip_honorifics,
}


def normalize_fields(fields: dict[str, RawExtraction]) -> dict[str, RawExtraction]:
    """Apply field normalizers in place-ish, returning the same mapping.
    `original_text` and `quotation` are untouched."""
    for name, raw in fields.items():
        normalizer = NORMALIZERS.get(name)
        if normalizer and raw.value:
            raw.value = normalizer(raw.value)
    return fields
