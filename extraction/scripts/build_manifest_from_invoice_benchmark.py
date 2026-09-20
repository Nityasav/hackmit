"""Build a labeled manifest from the invoice-sandbox-benchmark's answer key
(https://github.com/ciru-ai/invoice-sandbox-benchmark).

That benchmark ships `answer_key/invoices.csv` with per-document ground truth
— document_id, invoice_date, subtotal_usd, tax_usd, total_usd — which makes
it the one real, human-independent label source available right now for the
invoice schema. Labels are tagged `imported_ground_truth`, not
`human_verified`: they were authored by the benchmark, not reviewed by us.

Scope note: that benchmark is accounts *receivable* (invoices issued to
customers), while extraction/schemas/invoice.py is written for accounts
payable (invoices received from vendors). Only the fields whose meaning is
identical in both directions are imported — invoice number, dates, subtotal,
tax, total. `vendor_name` is deliberately NOT imported: the answer key's
`customer_name` is who was billed, which is not the same fact as who issued
the invoice, and mapping one onto the other would silently score a correct
extraction as wrong.

Usage:
    python scripts/build_manifest_from_invoice_benchmark.py \
        /path/to/invoice-sandbox-benchmark --out manifest_invoices.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.manifest_schema import DifficultyTag, LabelSource, Manifest, ManifestEntry  # noqa: E402
from schemas import invoice  # noqa: E402

# answer_key column -> our schema field. Deliberately partial; see module docstring.
FIELD_MAP = {
    "document_id": "invoice_number",
    "invoice_date": "invoice_date",
    "subtotal_usd": "subtotal",
    "tax_usd": "tax",
    "total_usd": "total",
}

# Fields our schema defines that this benchmark genuinely has no value for.
# Labeling them None makes correct abstention a scored behavior rather than
# an untested one.
KNOWN_ABSENT = ["service_date", "purchase_order_reference", "receipt_reference"]

STATUS_TAGS = {
    "VOID": DifficultyTag.clean,
    "SUPERSEDED": DifficultyTag.conflicting_dates,
    "DUPLICATE_SCAN": DifficultyTag.similar_ids_across_vendors,
    "CREDIT": DifficultyTag.credit_or_negative_amount,
    "STATEMENT": DifficultyTag.clean,
}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def template_family(filename: str) -> str:
    """Group key for held-out splitting. Files here are named
    INV-2025-1001_C011.pdf / statement_C003_2025_Q3.pdf / CM-2025-077_C001.pdf,
    so the customer id is the closest available stand-in for an
    institution/template family. Everything for one customer stays on one
    side of the split."""
    match = re.search(r"_(C\d{3})", filename)
    if match:
        return f"customer:{match.group(1)}"
    return "customer:unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark_root")
    parser.add_argument("--out", default="manifest_invoices.json")
    parser.add_argument("--source", default="gold_master", help="gold_master, or runs/<id>/workspace")
    args = parser.parse_args()

    root = Path(args.benchmark_root)
    answer_key = root / "answer_key" / "invoices.csv"
    docs_root = root / args.source

    entries: list[ManifestEntry] = []
    with answer_key.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            pdf_path = docs_root / row["file_path"]
            if not pdf_path.is_file():
                continue

            expected: dict[str, str | None] = {}
            for column, field_name in FIELD_MAP.items():
                value = (row.get(column) or "").strip()
                expected[field_name] = value or None
            for field_name in KNOWN_ABSENT:
                expected[field_name] = None

            tags = [DifficultyTag.multipage]  # every packet here is multipage
            status_tag = STATUS_TAGS.get((row.get("status") or "").strip())
            if status_tag and status_tag not in tags:
                tags.append(status_tag)

            entries.append(
                ManifestEntry(
                    example_id=row["file_path"],
                    document_path=str(pdf_path),
                    document_hash=file_hash(pdf_path),
                    document_type="invoice",
                    schema_version=invoice.SCHEMA_VERSION,
                    page=1,
                    expected_fields=expected,
                    label_source=LabelSource.imported_ground_truth,
                    labeled_by="invoice-sandbox-benchmark answer_key",
                    split_key=template_family(row["file_path"]),
                    difficulty_tags=tags,
                    notes=f"answer_key status={row.get('status')} policy={row.get('policy')}",
                )
            )

    manifest = Manifest(dataset_version="invoice-sandbox-benchmark-v1", entries=entries)
    Path(args.out).write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    print(f"wrote {len(entries)} entries -> {args.out}")
    print(f"split_keys: {len(manifest.split_keys())}")
    print(f"coverage by tag: {json.dumps(manifest.coverage_by_tag(), indent=2)}")


if __name__ == "__main__":
    main()
