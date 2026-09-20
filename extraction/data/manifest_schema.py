"""One training/evaluation example's required shape (spec.md §7.5 steps 1-2:
capture, then qualify).

An example is only admissible when its labels are human-verified and its
quotations resolve to the original source. `label_source` makes the
provenance explicit and un-fudgeable: `model_proposed` labels are a draft
queued for review, never training truth. spec.md is blunt about why —
"production outputs must never recursively become training truth merely
because the model generated them" — so `is_admissible()` refuses anything
that hasn't been through a human.

`split_key` is what held-out splitting groups on. It must identify the
institution / vendor / template family, never the individual page: two pages
of the same invoice, or two invoices off the same template, leaking across
a train/test boundary turns the evaluation into a memorization check.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LabelSource(str, Enum):
    human_authored = "human_authored"
    human_verified = "human_verified"  # model or import proposed it, a human checked and corrected it
    model_proposed = "model_proposed"  # NOT admissible for training; review queue only
    imported_ground_truth = "imported_ground_truth"  # e.g. a benchmark's own answer key


class DifficultyTag(str, Enum):
    """The brief's required hard cases. Track coverage so a "clean documents
    only" dataset can't quietly pass for a representative one."""

    clean = "clean"
    scan = "scan"
    rotated_page = "rotated_page"
    messy_table = "messy_table"
    multipage = "multipage"
    missing_fields = "missing_fields"
    unreadable_text = "unreadable_text"
    date_confusion = "date_confusion"  # invoice vs service vs payment date
    similar_ids_across_vendors = "similar_ids_across_vendors"
    credit_or_negative_amount = "credit_or_negative_amount"
    foreign_currency = "foreign_currency"
    grant_amendment = "grant_amendment"
    conflicting_dates = "conflicting_dates"
    embedded_instructions = "embedded_instructions"  # prompt injection: treat as text, never commands


class ManifestEntry(BaseModel):
    """One document + requested schema -> verified expected output."""

    model_config = ConfigDict(extra="forbid")

    example_id: str
    document_path: str
    document_hash: str
    document_type: str  # "invoice" | "grant_agreement" | "service_record"
    schema_version: str

    # Which page(s) the labels describe. Extraction is per-page for PDFs.
    page: int = 1

    # {field_name: expected value string or None}. None means the field is
    # genuinely absent — correctly abstaining on it is a scored behavior, not
    # a gap in the labels.
    expected_fields: dict[str, str | None]

    label_source: LabelSource
    labeled_by: str | None = None
    labeled_at: str | None = None

    split_key: str  # institution / vendor / template family — never a page id
    difficulty_tags: list[DifficultyTag] = Field(default_factory=list)
    notes: str | None = None

    def is_admissible_for_training(self) -> bool:
        """spec.md §7.5 step 2: only human-approved labels train a candidate."""
        return self.label_source in (
            LabelSource.human_authored,
            LabelSource.human_verified,
            LabelSource.imported_ground_truth,
        )


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_version: str
    entries: list[ManifestEntry]

    def admissible(self) -> list[ManifestEntry]:
        return [e for e in self.entries if e.is_admissible_for_training()]

    def split_keys(self) -> set[str]:
        return {e.split_key for e in self.entries}

    def coverage_by_tag(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.entries:
            for tag in entry.difficulty_tags:
                counts[tag.value] = counts.get(tag.value, 0) + 1
        return counts


def split_by_key(
    manifest: Manifest, holdout_keys: set[str]
) -> tuple[list[ManifestEntry], list[ManifestEntry]]:
    """Group-wise split. Every entry sharing a split_key lands on the same
    side — this is the only splitting function here on purpose, because a
    random page-level split is the failure mode the brief calls out by name
    ("Split evaluation by institution/vendor/template, not random pages")."""
    train = [e for e in manifest.entries if e.split_key not in holdout_keys]
    holdout = [e for e in manifest.entries if e.split_key in holdout_keys]
    return train, holdout


def assert_no_leakage(train: list[ManifestEntry], holdout: list[ManifestEntry]) -> None:
    overlap = {e.split_key for e in train} & {e.split_key for e in holdout}
    if overlap:
        raise ValueError(f"split_key leakage between train and holdout: {sorted(overlap)}")


def load_manifest(path: str) -> Manifest:
    import json
    from pathlib import Path

    return Manifest.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
