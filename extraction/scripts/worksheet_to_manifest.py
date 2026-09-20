"""Turn a filled-in labeling worksheet into a manifest the benchmark scores.

This is the bridge between a human with a spreadsheet and the evaluation
pipeline. Labels come out as `human_verified`, which is what makes them
admissible (spec.md §7.5 step 2) — the auto-filled columns were produced by
deterministic regex, never by the model under evaluation, and a human
confirmed them.

Blank cell semantics matter and are deliberate: a blank means the field is
genuinely ABSENT in the document, and gets labeled None so that correctly
producing nothing scores as `correct_abstention`. If you meant "I haven't
looked at this yet", don't import the row — an unlabeled field imported as
absent will score a correct extraction as `over_extracted`, which is the
worst kind of wrong number because it looks like a model failure.

Usage:
    python scripts/worksheet_to_manifest.py data/apex_labeling_worksheet.csv \
        --pdf-dir data/apex_invoices --out manifest_apex.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.manifest_schema import DifficultyTag, LabelSource, Manifest, ManifestEntry  # noqa: E402
from schemas import invoice  # noqa: E402


# Earlier worksheet drafts encoded instructions into the column names. Strip
# them so a sheet someone already started labeling still imports.
_COLUMN_SUFFIXES = ("__JUDGMENT", "__CONFIRM_NONE", "__asprinted")


def normalize_column(name: str) -> str:
    for suffix in _COLUMN_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def normalize_cell(value: object) -> str:
    """Spreadsheets retype cells on you: Numbers turns 3500.00 into a float
    and a date string into a datetime. Money must survive as an exact decimal
    string (a float that prints as '3500.0' is fine numerically but stops
    being the document's text), and dates normalize to ISO, which
    evaluate.py compares correctly against either form."""
    import datetime as _dt
    from decimal import Decimal

    if value is None:
        return ""
    if isinstance(value, _dt.datetime):
        return value.date().isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, float):
        return str(Decimal(str(value)).quantize(Decimal("0.01")))
    if isinstance(value, int):
        return str(value)
    return str(value).strip()


def split_key_for(filename: str) -> str:
    """Group by issuing vendor — the whole point of this dataset is that it
    has three of them, unlike the single-template set. Filenames are
    Avila_..., Kao_..., Westfield_...
    """
    return f"vendor:{filename.split('_')[0]}"


def load_rows(path: Path) -> list[dict[str, str]]:
    """Accepts .csv or Apple .numbers — people label in whatever they have."""
    if path.suffix.lower() == ".numbers":
        from numbers_parser import Document

        table = Document(str(path)).sheets[0].tables[0]
        raw = table.rows(values_only=True)
        header = [normalize_column(str(c)) for c in raw[0]]
        return [
            {key: normalize_cell(cell) for key, cell in zip(header, row)}
            for row in raw[1:]
            if row and row[0]
        ]

    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return [
            {normalize_column(k): normalize_cell(v) for k, v in row.items() if k}
            for row in reader
        ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("worksheet", help=".csv or Apple .numbers")
    parser.add_argument("--pdf-dir", required=True)
    parser.add_argument("--out", default="manifest_apex.json")
    parser.add_argument("--labeled-by", default="", help="Recorded on every entry.")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Import rows whose auto-filled fields are blank. Off by default: a blank "
        "auto field usually means the regex missed, not that the value is absent.",
    )
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir)
    rows = load_rows(Path(args.worksheet))
    if not rows:
        raise SystemExit("worksheet is empty")

    label_fields = [c for c in rows[0] if c != "file" and not c.startswith("_")]
    unknown = set(label_fields) - set(invoice.SCALAR_FIELDS)
    if unknown:
        raise SystemExit(f"worksheet has columns that aren't invoice schema fields: {sorted(unknown)}")

    entries: list[ManifestEntry] = []
    skipped: list[str] = []

    for row in rows:
        filename = (row.get("file") or "").strip()
        pdf_path = pdf_dir / filename
        if not filename or not pdf_path.is_file():
            skipped.append(f"{filename or '(no file)'}: PDF not found")
            continue

        # A row where the machine-extractable fields are empty is almost
        # certainly unreviewed rather than genuinely blank.
        if not args.allow_partial and not (row.get("invoice_number") or "").strip():
            skipped.append(f"{filename}: invoice_number blank (use --allow-partial to force)")
            continue

        expected: dict[str, str | None] = {}
        for field in invoice.SCALAR_FIELDS:
            value = (row.get(field) or "").strip() if field in label_fields else ""
            expected[field] = value or None

        tags = [DifficultyTag.clean]
        if expected.get("tax") is None:
            tags.append(DifficultyTag.missing_fields)

        entries.append(
            ManifestEntry(
                example_id=filename,
                document_path=str(pdf_path.resolve()),
                document_hash=hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                document_type="invoice",
                schema_version=invoice.SCHEMA_VERSION,
                page=1,
                expected_fields=expected,
                label_source=LabelSource.human_verified,
                labeled_by=args.labeled_by or None,
                split_key=split_key_for(filename),
                difficulty_tags=tags,
                notes="mercor/apex-accounting (CC BY 4.0) contract-attorney invoice",
            )
        )

    if not entries:
        raise SystemExit("no rows imported:\n  " + "\n  ".join(skipped))

    manifest = Manifest(dataset_version="apex-contract-attorney-v1", entries=entries)
    Path(args.out).write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    absent = sum(1 for e in entries for v in e.expected_fields.values() if v is None)
    present = sum(1 for e in entries for v in e.expected_fields.values() if v is not None)
    print(f"wrote {len(entries)} entries -> {args.out}")
    print(f"  split groups (vendors): {sorted(manifest.split_keys())}")
    print(f"  labeled values: {present} present, {absent} absent (absent = abstention tests)")
    if skipped:
        print(f"  skipped {len(skipped)}:")
        for reason in skipped:
            print(f"    {reason}")
    print(f"\nNext:\n  python scripts/benchmark_base_model.py {args.out} --batch-size 4 --skip-list-fields --out predictions_apex.json")


if __name__ == "__main__":
    main()
