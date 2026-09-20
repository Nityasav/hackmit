"""Sampling and tracing: what D1 does, and what it refuses to claim it has shown.

Two failure modes are being guarded against here, and neither one looks like a bug when
it happens. A sample that quietly misses the largest item reads exactly like a sample that
covered everything. A trail with a step omitted reads exactly like a trail with one fewer
step. Both tests below exist to keep those pairs distinguishable.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app import ingestion
from app.accounting import audit

REPO = Path(__file__).resolve().parents[2]
PERIOD = "2026-09"


@pytest.fixture(scope="module")
def pack(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("audit")
    result = subprocess.run(
        [sys.executable, str(REPO / "fixtures" / "generate_saas.py"),
         "--out", str(out), "--seed", "2026", "--periods", PERIOD],
        capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    return out / PERIOD


@pytest.fixture
def ws(tmp_path, monkeypatch, pack) -> str:
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path / "data"))
    workspace = ingestion.create_workspace(ingestion.WorkspaceCreate(
        name="Halden Cloud Inc.", start="2026-09-01", end="2026-09-30", scope="Audit",
        settings={"approval_limit_cents": 500_000, "materiality_cents": 100_000}))["id"]
    batch = ingestion.stage(workspace, [
        (p.name, p.read_bytes(), ingestion.FileOptions(role=p.stem))
        for p in sorted(pack.glob("*.csv"))])
    assert batch["status"] == "ready_to_commit", batch["issues"][:3]
    ingestion.commit(workspace, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key="audit"))
    return workspace


def _records(ws: str) -> list[dict]:
    return ingestion.financial_records(ws)["records"]


def _config(ws: str) -> dict:
    return ingestion.workspace_config(ws)


# --------------------------------------------------------------------------- #
# Sampling
# --------------------------------------------------------------------------- #

def test_the_same_population_and_seed_give_the_same_sample(ws):
    """A selection a reader cannot reproduce is a selection they have to take on trust."""
    records, config = _records(ws), _config(ws)

    first = audit.select(records, config, seed="fixed")
    second = audit.select(records, config, seed="fixed")

    assert [i["record_key"] for i in first["selected"]] == \
        [i["record_key"] for i in second["selected"]]


def test_the_selection_does_not_depend_on_the_order_records_arrived_in(ws):
    """Re-uploading the same period with the files in a different order must not
    silently change which transactions were tested."""
    records, config = _records(ws), _config(ws)

    forwards = audit.select(records, config, seed="fixed")
    backwards = audit.select(list(reversed(records)), config, seed="fixed")

    assert sorted(i["record_key"] for i in forwards["selected"]) == \
        sorted(i["record_key"] for i in backwards["selected"])


def test_everything_material_is_taken_in_full_rather_than_sampled(ws):
    """A test that might miss the largest item is not a test of the largest item."""
    records, config = _records(ws), _config(ws)
    materiality = config["settings"]["materiality_cents"]

    result = audit.select(records, config, size=1, seed="fixed")
    material = {i["record_key"] for i in result["selected"] if i["stratum"] == "material"}

    for record in records:
        if record["role"] != "vendor_invoices":
            continue
        if abs(record["payload"].get("amount_cents", 0)) >= materiality:
            assert record["record_key"] in material


def test_the_sample_reports_its_method_beside_itself(ws):
    result = audit.select(_records(ws), _config(ws), seed="fixed")

    assert result["method"]["seed"] == "fixed"
    assert result["method"]["material_threshold_cents"] > 0
    assert result["method"]["how"]
    assert "say nothing about the items that were not" in result["note"]


def test_coverage_is_floored_rather_than_rounded_up(ws):
    """Coverage rounded up reads as more assurance than the sample supports."""
    result = audit.select(_records(ws), _config(ws), size=3, seed="fixed")

    assert result["coverage_pct"] == (
        result["selected_cents"] * 100 // result["population_cents"])
    assert result["coverage_pct"] <= 100


def test_a_population_with_no_materiality_says_the_largest_item_may_be_missing(ws):
    config = dict(_config(ws))
    config["settings"] = {}

    result = audit.select(_records(ws), config, seed="fixed")

    assert result["method"]["material_taken_in_full"] == 0
    assert "largest item may not be in it" in result["note"]


# --------------------------------------------------------------------------- #
# Tracing
# --------------------------------------------------------------------------- #

def _some_invoice(ws: str) -> str:
    return next(r["record_key"] for r in _records(ws) if r["role"] == "vendor_invoices")


def test_a_purchase_traces_from_its_order_to_its_ledger_entries(ws):
    result = audit.trace(_records(ws), _some_invoice(ws))

    assert result["found"]
    assert [step["role"] for step in result["steps"]] == \
        [role for role, _ in audit.PURCHASE_TRAIL]
    for step in result["steps"]:
        if step["present"]:
            assert step["records"] and step["evidence"]
            assert step["linked_by"]


def test_a_missing_step_is_named_rather_than_skipped(ws):
    """A trail with a hole and a trail with one fewer step look identical once the hole
    is left out."""
    records = _records(ws)
    key = _some_invoice(ws)
    without_receipts = [r for r in records if r["role"] != "goods_receipts"]

    result = audit.trace(without_receipts, key)

    assert not result["complete"]
    assert "goods_receipts" in result["missing"]
    assert any(step["role"] == "goods_receipts" and not step["present"]
               for step in result["steps"])
    assert "The trail stops" in result["note"]


def test_a_complete_trail_says_what_it_does_not_establish(ws):
    records = _records(ws)
    complete = next(
        (audit.trace(records, r["record_key"]) for r in records
         if r["role"] == "vendor_invoices" and audit.trace(records, r["record_key"])["complete"]),
        None)
    assert complete, "the generated period must contain one fully documented purchase"

    assert "internally consistent" in complete["note"]
    assert "transaction was genuine" in complete["does_not_establish"]


def test_an_invoice_that_does_not_exist_is_refused_rather_than_traced_emptily(ws):
    """An empty trail for a missing invoice would read as a transaction with no evidence
    behind it, which is a different and much more alarming thing."""
    result = audit.trace(_records(ws), "VI-DOES-NOT-EXIST")

    assert not result["found"]
    assert not result["complete"]
    assert "No such vendor invoice" in result["note"]
