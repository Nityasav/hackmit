"""The phase-1 gate: generated books import, tie, and drive what Books asks for.

These tests go through the real staging, mapping and commit path with bytes the
generator wrote, so nothing here is proved against data a test authored by hand.

What is deliberately *not* asserted: that the books are complete, or that any finding
follows from them. Intake decides whether records are well formed. Everything else is
the accounting engine's job and the agents'.
"""

from __future__ import annotations

import csv
import io
import subprocess
import sys
from pathlib import Path

import pytest

from app import db, ingestion, requirements, roles

REPO = Path(__file__).resolve().parents[2]
PERIOD = "2026-09"


@pytest.fixture(scope="module")
def generated(tmp_path_factory) -> Path:
    """One generated period, produced by running the generator as a person would."""
    out = tmp_path_factory.mktemp("generated")
    result = subprocess.run(
        [sys.executable, str(REPO / "fixtures" / "generate_saas.py"),
         "--out", str(out), "--seed", "11", "--periods", PERIOD],
        capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return out / PERIOD


@pytest.fixture
def workspace(tmp_path, monkeypatch) -> str:
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path / "data"))
    created = ingestion.create_workspace(ingestion.WorkspaceCreate(
        name="Halden Cloud Inc.", kind="synthetic", entity_type="company",
        jurisdiction="US-CA", currency="USD",
        start="2026-09-01", end="2026-09-30", scope="September close",
    ))
    return created["id"]


def _upload(path: Path, role: str) -> tuple[str, bytes, ingestion.FileOptions]:
    return path.name, path.read_bytes(), ingestion.FileOptions(role=role, source_system="generator")


def _commit_all(ws: str, generated: Path, roles_wanted: list[str]) -> dict:
    uploads = [_upload(generated / f"{role}.csv", role) for role in roles_wanted
               if (generated / f"{role}.csv").exists()]
    batch = ingestion.stage(ws, uploads)
    assert batch["status"] == "ready_to_commit", [i["message"] for i in batch["issues"][:5]]
    return ingestion.commit(ws, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key="phase-1"))


# --------------------------------------------------------------------------- #
# The generator's own output
# --------------------------------------------------------------------------- #

def test_the_generator_writes_a_file_for_every_role_it_claims(generated):
    written = {p.stem for p in generated.glob("*.csv")}
    unknown = written - set(roles.FIELDS)
    assert not unknown, f"generated files with no intake role: {sorted(unknown)}"
    # The spine plus both cash directions, or a period has nothing to reconcile.
    assert {"chart", "opening", "ledger", "vendor_invoices", "payments",
            "customer_invoices", "remittances", "bank_transactions"} <= written


def test_every_period_moves_cash_in_both_directions(generated):
    with (generated / "bank_transactions.csv").open(encoding="utf-8-sig", newline="") as handle:
        directions = {row["direction"] for row in csv.DictReader(handle)}
    assert directions == {"in", "out"}, "a period with one-way cash cannot be reconciled"


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #

def test_the_ledger_spine_commits_and_publishes_a_snapshot(workspace, generated):
    committed = _commit_all(workspace, generated, ["chart", "opening", "ledger"])

    assert committed["status"] == "committed"
    assert committed["snapshot_id"], "committing new records must publish a snapshot"
    assert committed["counts"]["new_records"] > 0
    # The balance control intake enforces: a journal that does not balance is refused,
    # so a committed ledger is balanced by construction.
    assert committed["totals"]["debit_cents"] == committed["totals"]["credit_cents"]


def test_the_whole_period_commits_in_one_batch(workspace, generated):
    every_role = [p.stem for p in sorted(generated.glob("*.csv"))]
    committed = _commit_all(workspace, generated, every_role)

    assert committed["status"] == "committed"
    coverage = ingestion.coverage(workspace)
    present = {source["role"] for source in coverage["sources"] if source["active"]}
    assert present == set(every_role), sorted(set(every_role) - present)


def test_a_second_commit_of_the_same_files_adds_no_records(workspace, generated):
    """Re-uploading the same bytes is a duplicate, not new activity."""
    _commit_all(workspace, generated, ["chart", "opening", "ledger"])
    before = ingestion.coverage(workspace)["snapshot"]["id"]

    uploads = [_upload(generated / f"{role}.csv", role) for role in ("chart", "opening", "ledger")]
    batch = ingestion.stage(workspace, uploads)
    committed = ingestion.commit(workspace, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key="again"))

    assert committed["counts"]["new_records"] == 0
    assert committed["counts"]["duplicate_records"] > 0
    assert ingestion.coverage(workspace)["snapshot"]["id"] == before, \
        "a duplicate-only import must not publish a new snapshot"


# --------------------------------------------------------------------------- #
# Validation refuses what it should
# --------------------------------------------------------------------------- #

def _staged(ws: str, name: str, role: str, content: str) -> dict:
    return ingestion.stage(ws, [(name, content.encode(), ingestion.FileOptions(role=role))])


def test_an_unbalanced_journal_is_refused(workspace, generated):
    _commit_all(workspace, generated, ["chart"])
    batch = _staged(workspace, "bad.csv", "ledger",
                    "entry_id,line_id,date,account,debit,credit\n"
                    "JE-X,1,2026-09-10,6100,500.00,0.00\n"
                    "JE-X,2,2026-09-10,1000,0.00,400.00\n")
    codes = {issue["code"] for issue in batch["issues"]}
    assert "unbalanced_journal" in codes
    assert batch["status"] != "ready_to_commit"


def test_a_payout_that_does_not_decompose_is_refused(workspace):
    batch = _staged(workspace, "payouts.csv", "processor_payouts",
                    "payout_id,processor,payout_date,gross,fees,refunds,chargebacks,net\n"
                    "PO-1,card_processor,2026-09-10,1000.00,30.00,0.00,0.00,999.00\n")
    assert "payout_identity" in {issue["code"] for issue in batch["issues"]}


def test_payroll_that_does_not_tie_is_refused(workspace):
    batch = _staged(workspace, "payroll.csv", "payroll",
                    "record_id,employee_id,period_start,period_end,pay_date,gross,deductions,net,employer_cost\n"
                    "PR-1,E-1,2026-09-01,2026-09-30,2026-09-28,5000.00,1000.00,4500.00,575.00\n")
    assert "payroll_tie" in {issue["code"] for issue in batch["issues"]}


def test_a_signed_bank_amount_is_refused_rather_than_reinterpreted(workspace):
    """Direction is a column. A minus sign must never silently reverse a transaction."""
    batch = _staged(workspace, "bank.csv", "bank_transactions",
                    "bank_id,bank_account,settlement_date,direction,amount,description\n"
                    "BK-1,Operating,2026-09-10,out,-500.00,REVERSAL\n")
    assert batch["status"] != "ready_to_commit"
    assert {"invalid_value", "bank_direction"} & {issue["code"] for issue in batch["issues"]}


def test_a_budget_against_an_unknown_account_is_refused(workspace, generated):
    """Caught at import, because finding it at variance time is too late."""
    _commit_all(workspace, generated, ["chart"])
    batch = _staged(workspace, "budgets.csv", "budgets",
                    "record_id,account,period,amount,approval_reference\n"
                    "BU-1,9999,2026-09,1000.00,BOARD-1\n")
    assert "unknown_account" in {issue["code"] for issue in batch["issues"]}


# --------------------------------------------------------------------------- #
# Requirements drive Books
# --------------------------------------------------------------------------- #

def test_an_empty_workspace_reports_every_requirement_as_missing(workspace):
    view = ingestion.coverage(workspace)

    assert view["satisfied_count"] == 0
    assert view["required_count"] > 0
    assert all(not r["satisfied"] for r in view["requirements"])
    # And it says who is waiting, not merely that something is absent.
    assert view["blocked_agents"], "a missing input must name the agents it blocks"


def test_committing_records_satisfies_their_requirement_and_unblocks_agents(workspace, generated):
    before = ingestion.coverage(workspace)
    assert "A1" in before["blocked_agents"]

    _commit_all(workspace, generated, ["chart", "opening", "ledger", "vendors",
                                       "purchase_orders", "goods_receipts",
                                       "vendor_invoices", "payments", "approvals"])
    after = ingestion.coverage(workspace)

    satisfied = {r["id"] for r in after["requirements"] if r["satisfied"]}
    assert {"chart", "ledger", "vendors", "vendor_invoices", "purchase_orders"} <= satisfied
    assert after["satisfied_count"] > before["satisfied_count"]
    # A1 still needs the policy it tests against and the limit above which a payment
    # needs a person. Both are real dependencies, and Books is now asking for exactly
    # those two rather than repeating everything A1 ever wanted.
    assert after["blocked_agents"].get("A1") == ["approval_limit_cents", "policy"]


def test_a_setting_is_answered_in_books_rather_than_uploaded(workspace):
    blocked = ingestion.coverage(workspace)["blocked_agents"]
    assert "materiality_cents" in blocked["D1"]

    updated = ingestion.update_settings(workspace, ingestion.SettingsUpdate(
        settings={"materiality_cents": 250_000, "home_jurisdiction": "US-CA"}))

    answered = {r["id"]: r for r in updated["requirements"]}
    assert answered["materiality_cents"]["satisfied"]
    assert answered["materiality_cents"]["value"] == 250_000
    assert "materiality_cents" not in updated["blocked_agents"].get("D1", [])


def test_clearing_a_setting_makes_it_unanswered_again(workspace):
    ingestion.update_settings(workspace, ingestion.SettingsUpdate(
        settings={"home_jurisdiction": "US-CA"}))
    cleared = ingestion.update_settings(workspace, ingestion.SettingsUpdate(
        settings={"home_jurisdiction": "  "}))

    answered = {r["id"]: r for r in cleared["requirements"]}
    assert not answered["home_jurisdiction"]["satisfied"]
    assert answered["home_jurisdiction"]["value"] is None


def test_an_unknown_setting_is_refused(workspace):
    with pytest.raises(ValueError, match="Unknown setting"):
        ingestion.SettingsUpdate(settings={"pay_everyone_more": "yes"})


def test_a_money_setting_must_be_a_whole_number_of_cents(workspace):
    with pytest.raises(ValueError, match="whole number"):
        ingestion.SettingsUpdate(settings={"materiality_cents": "2500.00"})


# --------------------------------------------------------------------------- #
# Registry consistency
# --------------------------------------------------------------------------- #

def test_every_requirement_names_a_role_intake_accepts():
    for requirement in requirements.REQUIREMENTS:
        if requirement.kind == "setting":
            continue
        assert requirement.role in roles.FIELDS or requirement.role in roles.DOCUMENT_ROLES


def test_every_structured_role_has_a_key_and_a_label():
    for role in roles.FIELDS:
        assert role in roles.KEY_FIELDS, f"{role} has no business key"
        assert role in roles.LABELS, f"{role} has no display label"
        missing = set(roles.KEY_FIELDS[role]) - set(roles.FIELDS[role])
        assert not missing, f"{role} keys on columns it does not require: {missing}"


def test_a_composite_key_cannot_collide_with_a_single_one():
    """`(PO-1, 2)` and `(PO-1|2,)` must not be the same record."""
    first = roles.key_of("purchase_orders", {"po_id": "PO-1", "line_id": "2"})
    second = roles.key_of("purchase_orders", {"po_id": "PO-1|2", "line_id": ""})
    assert first != second


def test_the_event_column_survives_import(workspace, generated):
    """`event_ref` is how the event graph is bootstrapped, so it must reach the record."""
    _commit_all(workspace, generated, ["chart", "opening", "ledger"])
    with db.connect() as connection:
        rows = ingestion.active_records(connection, workspace)
    ledger = [r for r in rows if r["role"] == "ledger"]
    assert ledger and all(r["payload"].get("event_ref") for r in ledger)
