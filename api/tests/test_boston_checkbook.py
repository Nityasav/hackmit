"""The Boston loader: what it maps, what it derives, and what it refuses to guess.

Nothing here touches the network. The fixture is a handful of rows in Checkbook
Explorer's published shape, and the properties asserted are the ones that make
the difference between a loader and a fabricator: a voucher is taken whole or
not at all, a derived line says it is derived, and every row that did not make
it is counted rather than swallowed.

The last test is the one that matters most — the bytes the loader writes go
through the real staging path and have to come out `ready_to_commit`. A loader
whose output needs a special case at intake is a broken loader.
"""

from __future__ import annotations

import csv
import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest

from app import ingestion

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_boston_checkbook.py"
_spec = importlib.util.spec_from_file_location("fetch_boston_checkbook", SCRIPT)
boston = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(boston)

START, END = "2023-07-01", "2023-07-31"


def row(voucher, vline, dline, entered, vendor, account, descr, dept, amount):
    return {"Voucher": voucher, "Voucher Line": vline, "Distribution Line": dline,
            "Entered": entered, "Vendor Name": vendor, "Account": account,
            "Account Descr": descr, "Dept Name": dept, "Monetary Amount": amount}


@pytest.fixture
def rows():
    return [
        # An ordinary two-line voucher.
        row("3315540", "1", "1", "7/5/2023", "PJ Systems Inc.", "55903", "Equipment Computer/Desktop", "Boston Public School Dept", "1375"),
        row("3315540", "2", "1", "7/5/2023", "PJ Systems Inc.", "55903", "Equipment Computer/Desktop", "Boston Public School Dept", "625"),
        # A credit: money coming back, which is a credit to the expense account.
        row("3315600", "1", "1", "7/6/2023", "Northeast Supply", "52700", "Repairs Buildings", "Public Works Dept", "-482.15"),
        # Two vouchers, one vendor, one day, one amount: a duplicate *candidate*.
        row("3316527", "1", "1", "7/6/2023", "Boston After School & Beyond", "53000", "Contracted Services", "Boston Public School Dept", "37500"),
        row("3316537", "1", "1", "7/6/2023", "Boston After School & Beyond", "53000", "Contracted Services", "Boston Public School Dept", "37500"),
        # Lines entered on two different dates.
        row("3317000", "1", "1", "7/7/2023", "Harbor Fuel Co.", "52200", "Heating Fuel", "Property Mgmt Dept", "900"),
        row("3317000", "2", "1", "7/8/2023", "Harbor Fuel Co.", "52200", "Heating Fuel", "Property Mgmt Dept", "100"),
        # A zero line.
        row("3317100", "1", "1", "7/9/2023", "Quiet Vendor LLC", "53000", "Contracted Services", "Public Works Dept", "0"),
        # A voucher that already nets to zero.
        row("3317200", "1", "1", "7/10/2023", "Reversal Ltd", "53000", "Contracted Services", "Public Works Dept", "500"),
        row("3317200", "2", "1", "7/10/2023", "Reversal Ltd", "53000", "Contracted Services", "Public Works Dept", "-500"),
        # Outside the window.
        row("3320000", "1", "1", "8/2/2023", "Later Vendor", "53000", "Contracted Services", "Public Works Dept", "2500"),
    ]


@pytest.fixture
def ledger(rows):
    entries, _ = boston.journals(rows, START, END)
    return entries


def by_voucher(ledger):
    grouped = {}
    for line in ledger:
        grouped.setdefault(line[0], []).append(line)
    return grouped


def net(lines):
    return sum(Decimal(line[4]) - Decimal(line[5]) for line in lines)


# --------------------------------------------------------------------------- #
# Journals
# --------------------------------------------------------------------------- #

def test_every_journal_balances(ledger):
    for voucher, lines in by_voucher(ledger).items():
        assert net(lines) == 0, f"{voucher} does not balance"


def test_a_voucher_entered_on_two_dates_is_not_loaded(rows):
    entries, dropped = boston.journals(rows, START, END)
    assert "3317000" not in by_voucher(entries)
    # Counted, not swallowed: a total nobody can tie back to the published file
    # is the failure mode this guards.
    assert any("different dates" in line for line in dropped.lines())


def test_a_voucher_with_a_zero_line_is_not_loaded(rows):
    entries, dropped = boston.journals(rows, START, END)
    assert "3317100" not in by_voucher(entries)
    assert any("zero amount" in line for line in dropped.lines())


def test_a_voucher_that_already_nets_to_zero_gets_no_derived_line(ledger):
    lines = by_voucher(ledger)["3317200"]
    assert [line[1] for line in lines] == ["1-1", "2-1"]
    assert net(lines) == 0


def test_a_negative_amount_becomes_a_credit_not_a_negative_debit(ledger):
    expense, contra = by_voucher(ledger)["3315600"]
    assert (expense[4], expense[5]) == ("0.00", "482.15")
    assert (contra[4], contra[5]) == ("482.15", "0.00")


def test_a_voucher_outside_the_window_is_excluded_without_being_called_a_problem(rows):
    entries, dropped = boston.journals(rows, START, END)
    assert "3320000" not in by_voucher(entries)
    assert not any("3320000" in example for example in dropped.examples.values())


def test_published_lines_keep_their_voucher_and_distribution_numbers(ledger):
    lines = by_voucher(ledger)["3315540"]
    assert [line[1] for line in lines] == ["1-1", "2-1", "contra"]
    assert [line[3] for line in lines[:2]] == ["55903", "55903"]


def test_vendor_and_department_travel_with_the_line(ledger):
    first = by_voucher(ledger)["3315540"][0]
    assert first[6] == "PJ Systems Inc."
    assert first[7] == "Boston Public School Dept"


# --------------------------------------------------------------------------- #
# What is derived says so
# --------------------------------------------------------------------------- #

def test_every_derived_line_is_labelled_and_uses_a_code_no_boston_account_can_be(ledger, rows):
    derived = [line for line in ledger if line[1] == "contra"]
    assert derived
    for line in derived:
        assert line[3] == boston.PAYABLE[0]
        assert line[6] == boston.DERIVED_MEMO
    # Boston account codes are digits. A derived code that could collide with one
    # would put invented money under a real account.
    published = {r["Account"].strip() for r in rows}
    for code, *_ in (boston.PAYABLE, boston.CASH, boston.FUND):
        assert not code.isdigit()
        assert code not in published


def test_the_opening_balances_and_is_dated_at_the_start_of_the_period(ledger):
    balances = boston.opening(ledger, START)
    assert sum(Decimal(b[3]) - Decimal(b[4]) for b in balances) == 0
    assert {b[2] for b in balances} == {START}
    assert {b[1] for b in balances} == {boston.CASH[0], boston.FUND[0]}


def test_the_chart_covers_every_account_the_ledger_posts_to(ledger, rows):
    accounts, _ = boston.chart(rows, ledger, START)
    assert {line[3] for line in ledger} <= {a[0] for a in accounts}


def test_an_account_with_two_descriptions_is_reported_rather_than_silently_halved(rows, ledger):
    rows = rows + [row("3315540", "3", "1", "7/5/2023", "PJ Systems Inc.", "55903",
                       "Computer Equipment", "Boston Public School Dept", "10")]
    accounts, ambiguous = boston.chart(rows, ledger, START)
    assert len([a for a in accounts if a[0] == "55903"]) == 1
    assert any("55903" in line for line in ambiguous)


def test_a_duplicate_candidate_is_found_and_named_as_a_candidate(ledger):
    candidates = boston.duplicate_candidates(ledger)
    assert len(candidates) == 1
    assert "3316527" in candidates[0] and "3316537" in candidates[0]


# --------------------------------------------------------------------------- #
# Payments: the opt-in file, and the one column it costs
# --------------------------------------------------------------------------- #

def test_a_payment_carries_the_published_voucher_date_and_amount(ledger):
    paid, _ = boston.payments(ledger)
    row = next(p for p in paid if p[0] == "3315540")
    assert row[2] == "2023-07-05"
    assert row[4] == "2000.00"
    # A voucher number is the City's own payment reference. Both columns mean it.
    assert row[5] == "3315540"
    assert row[6] == "PJ Systems Inc."


def test_the_method_column_says_the_source_is_silent_rather_than_naming_one(ledger):
    paid, _ = boston.payments(ledger)
    assert {p[3] for p in paid} == {boston.UNSTATED}


def test_one_vendor_gets_one_id_across_its_vouchers(ledger):
    paid, _ = boston.payments(ledger)
    ids = {p[1] for p in paid if p[6] == "Boston After School & Beyond"}
    assert len(ids) == 1


def test_a_voucher_that_nets_to_a_credit_is_not_written_as_a_payment(ledger):
    paid, dropped = boston.payments(ledger)
    # 3315600 is a refund and 3317200 nets to zero. Neither is money going out.
    assert {p[0] for p in paid}.isdisjoint({"3315600", "3317200"})
    assert any("credit" in line for line in dropped.lines())


def test_a_voucher_paying_two_vendors_is_not_split_between_them(ledger):
    mixed = list(ledger) + [
        ["3399999", "1-1", "2023-07-12", "53000", "100.00", "0.00", "Vendor A", "Dept"],
        ["3399999", "2-1", "2023-07-12", "53000", "100.00", "0.00", "Vendor B", "Dept"],
    ]
    paid, dropped = boston.payments(mixed)
    assert "3399999" not in {p[0] for p in paid}
    assert any("single vendor" in line for line in dropped.lines())


# --------------------------------------------------------------------------- #
# The output goes through the real intake
# --------------------------------------------------------------------------- #

@pytest.fixture
def workspace(tmp_path, monkeypatch) -> str:
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path / "data"))
    created = ingestion.create_workspace(ingestion.WorkspaceCreate(
        name="City of Boston — Checkbook Explorer FY24",
        kind="open_data", entity_type="company", jurisdiction="US-MA", currency="USD",
        start=START, end=END, scope="July 2023 vouchers, published under the PDDL.",
    ))
    return created["id"]


def test_the_files_the_loader_writes_stage_as_ready_to_commit(rows, tmp_path, workspace):
    entries, _ = boston.journals(rows, START, END)
    accounts, _ = boston.chart(rows, entries, START)
    boston.write_csv(tmp_path / "chart-of-accounts.csv",
                     ["account", "name", "type", "report_mapping", "effective_from"], accounts)
    boston.write_csv(tmp_path / "opening-trial-balance.csv",
                     ["record_id", "account", "balance_date", "debit", "credit"],
                     boston.opening(entries, START))
    boston.write_csv(tmp_path / "general-ledger.csv",
                     ["entry_id", "line_id", "date", "account", "debit", "credit", "memo", "department"],
                     entries)

    paid, _ = boston.payments(entries)
    boston.write_csv(tmp_path / "payments.csv",
                     ["payment_id", "vendor_id", "payment_date", "method", "amount",
                      "reference", "memo"], paid)

    uploads = [(name, (tmp_path / name).read_bytes(),
                ingestion.FileOptions(role=role, source_system="boston_checkbook"))
               for name, role in boston.FILES]
    batch = ingestion.stage(workspace, uploads)
    assert batch["status"] == "ready_to_commit", [i["message"] for i in batch["issues"][:5]]

    committed = ingestion.commit(workspace, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key="boston-test"))
    assert committed["status"] == "committed"


def test_an_open_data_workspace_accepts_transactional_csv_and_is_not_called_synthetic(workspace):
    with ingestion.db.connect() as connection:
        config = ingestion.workspace(connection, workspace)
    assert config["kind"] == "open_data"
    assert config["profile"] == ingestion.PROFILE


def test_the_written_ledger_carries_the_vendor_a_reviewer_would_look_for(rows, tmp_path):
    entries, _ = boston.journals(rows, START, END)
    path = tmp_path / "general-ledger.csv"
    boston.write_csv(path, ["entry_id", "line_id", "date", "account", "debit", "credit",
                            "memo", "department"], entries)
    written = list(csv.DictReader(path.open()))
    published = [r for r in written if r["entry_id"] == "3316527" and r["line_id"] != "contra"]
    assert {r["memo"] for r in published} == {"Boston After School & Beyond"}
    # The contra line is the City's payable, not the vendor's invoice. It says what
    # it is instead of borrowing a name from the line above it.
    contra = [r for r in written if r["entry_id"] == "3316527" and r["line_id"] == "contra"]
    assert [r["memo"] for r in contra] == [boston.DERIVED_MEMO]
