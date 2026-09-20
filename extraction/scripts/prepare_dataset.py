"""Turn a manifest into TRL-ready supervised fine-tuning examples
(spec.md §7.5 step 3's input).

Each training example is (document page image + requested template) -> the
human-verified JSON the model should have produced. The target JSON is built
from the manifest's `expected_fields` in exactly the schema shape
schemas/*.py define, so the model is trained toward the same contract
scripts/evaluate.py scores against — a mismatch between those two is the
classic way to train a model that looks good in training and fails the
evaluation.

Only admissible entries are used: `model_proposed` labels are refused here,
not filtered silently, because "we accidentally trained on the model's own
unreviewed output" is precisely the feedback loop spec.md §7.5 forbids.

Usage:
    python scripts/prepare_dataset.py manifest.json --out train.jsonl --holdout-keys customer:C001,customer:C002
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.manifest_schema import (  # noqa: E402
    LabelSource,
    ManifestEntry,
    assert_no_leakage,
    load_manifest,
    split_by_key,
)
from schemas import grant_agreement, invoice, service_record  # noqa: E402

SCHEMA_MODULES = {
    "invoice": invoice,
    "grant_agreement": grant_agreement,
    "service_record": service_record,
}


def build_target_json(entry: ManifestEntry) -> dict:
    """The JSON the model should emit for this example, in the same wrapper
    shape schemas/template.py asks for. status/quotation mirror what the
    parser derives (see schemas/evidence.py): a labeled-absent field is
    `missing` with nulls, a labeled-present field is `present` quoting its
    own value. Locator is left null — the manifest doesn't carry per-field
    coordinates yet, and inventing them would teach the model to fabricate
    citations, which is the exact behavior evaluate.py penalizes."""
    target: dict[str, dict] = {}
    for field_name, value in entry.expected_fields.items():
        if value is None or not str(value).strip():
            target[field_name] = {
                "status": "missing",
                "value": None,
                "original_text": None,
                "quotation": None,
                "locator": None,
            }
        else:
            target[field_name] = {
                "status": "present",
                "value": value,
                "original_text": value,
                "quotation": value,
                "locator": {"page": entry.page, "row": None, "cell": None},
            }
    return target


def to_sft_record(entry: ManifestEntry) -> dict:
    module = SCHEMA_MODULES[entry.document_type]
    return {
        "example_id": entry.example_id,
        "document_path": entry.document_path,
        "page": entry.page,
        "template": module.template(),
        "target": build_target_json(entry),
        "split_key": entry.split_key,
        "schema_version": entry.schema_version,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--out", default="train.jsonl")
    parser.add_argument("--holdout-out", default=None, help="Write held-out entries here too.")
    parser.add_argument(
        "--holdout-keys",
        default="",
        help="Comma-separated split_keys held out. Grouped, never random (brief §5).",
    )
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)

    refused = [e for e in manifest.entries if e.label_source is LabelSource.model_proposed]
    if refused:
        raise SystemExit(
            f"{len(refused)} entries are label_source=model_proposed and cannot be trained on "
            f"(spec.md §7.5 step 2). Get them reviewed first: {[e.example_id for e in refused][:5]}"
        )

    holdout_keys = {k.strip() for k in args.holdout_keys.split(",") if k.strip()}
    train_entries, holdout_entries = split_by_key(manifest, holdout_keys)
    assert_no_leakage(train_entries, holdout_entries)

    with Path(args.out).open("w", encoding="utf-8") as f:
        for entry in train_entries:
            f.write(json.dumps(to_sft_record(entry)) + "\n")
    print(f"wrote {len(train_entries)} train records -> {args.out}")

    if args.holdout_out:
        with Path(args.holdout_out).open("w", encoding="utf-8") as f:
            for entry in holdout_entries:
                f.write(json.dumps(to_sft_record(entry)) + "\n")
        print(f"wrote {len(holdout_entries)} holdout records -> {args.holdout_out}")

    print(f"train split_keys: {len({e.split_key for e in train_entries})}")
    print(f"holdout split_keys: {len({e.split_key for e in holdout_entries})}")


if __name__ == "__main__":
    main()
