"""The phase-6 gate: a variance decomposes to named transactions.

The gate is deliberately narrow. It is easy to build something that reports a variance
and calls the report an explanation — a category, a percentage, a sentence. None of those
lets a person open the thing that caused it. So every test here ends at a record key or a
sum that has to come out exact.

Run against a generated period for the same reason `test_statements.py` is: a fixture
small enough to write by hand is small enough to make any arithmetic look right, and the
failures worth catching are the ones with somewhere to hide.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app import ingestion
from app.accounting import planning, reporting, statements, variance

REPO = Path(__file__).resolve().parents[2]
PERIOD = "2026-09"


@pytest.fixture(scope="module")
def pack(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("variance")
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
        name="Halden Cloud Inc.", start="2026-09-01", end="2026-09-30",
        scope="September review",
        settings={"approval_limit_cents": 500_000, "materiality_cents": 100_000}))["id"]
    batch = ingestion.stage(workspace, [
        (p.name, p.read_bytes(), ingestion.FileOptions(role=p.stem))
        for p in sorted(pack.glob("*.csv"))])
    assert batch["status"] == "ready_to_commit", batch["issues"][:3]
    ingestion.commit(workspace, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key="variance"))
    return workspace


def _records(ws: str) -> list[dict]:
    return ingestion.financial_records(ws)["records"]


def _config(ws: str) -> dict:
    return ingestion.workspace_config(ws)


def _biggest(ws: str) -> str:
    comparison = variance.budget_vs_actual(_records(ws), _config(ws))
    assert comparison["lines"], "the fixture must budget something for this to measure"
    return comparison["lines"][0]["account"]


def _most_detailed(ws: str) -> dict:
    """The account whose activity is made of the most separate transactions.

    The largest variance in this fixture is payroll, which is one monthly journal — so
    testing the gate against it would prove only that a decomposition of one thing
    returns one thing. The gate is about detail, so the test goes where the detail is.
    """
    records, config = _records(ws), _config(ws)
    decomposed = [variance.decompose(records, line["account"], config)
                  for line in variance.budget_vs_actual(records, config)["lines"]]
    return max(decomposed, key=lambda item: item["named_drivers"])


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #

def test_a_variance_decomposes_to_named_transactions(ws):
    """The whole phase in one assertion: every driver opens onto records."""
    result = _most_detailed(ws)

    assert result["found"]
    # Several, not one. A decomposition that returns the account back to you has
    # explained nothing, and would pass a weaker version of this test.
    assert result["named_drivers"] >= 3, result["account"]
    named = [d for d in result["drivers"] if d.get("event_ref")]
    assert len(named) == result["named_drivers"]
    for driver in named:
        assert driver["evidence"], driver["event_ref"]
        assert driver["entry_ids"], driver["event_ref"]
        for citation in driver["evidence"]:
            assert citation["record_key"] and citation["source_id"]


def test_each_driver_is_a_distinct_transaction(ws):
    """Two drivers pointing at one event would double-count it into the total."""
    result = _most_detailed(ws)
    named = [d["event_ref"] for d in result["drivers"] if d.get("event_ref")]

    assert len(named) == len(set(named))


def test_the_drivers_sum_to_the_actual_exactly(ws):
    """Not approximately, and not after a balancing item."""
    result = variance.decompose(_records(ws), _biggest(ws), _config(ws))

    assert sum(d["amount_cents"] for d in result["drivers"]) == result["actual_cents"]


def test_every_account_with_a_budget_decomposes_without_losing_a_cent(ws):
    """The identity holds across the whole period, not just the convenient account."""
    records, config = _records(ws), _config(ws)

    for line in variance.budget_vs_actual(records, config)["lines"]:
        result = variance.decompose(records, line["account"], config)
        assert sum(d["amount_cents"] for d in result["drivers"]) == result["actual_cents"], \
            line["account"]
        assert result["actual_cents"] == line["actual_cents"]


def test_a_small_driver_is_grouped_and_counted_rather_than_dropped(ws):
    """A tail that is dropped is how a decomposition comes out tidy and wrong."""
    account = _biggest(ws)
    records, config = _records(ws), _config(ws)

    # A floor high enough that everything falls below it: the group must then carry the
    # entire actual, and the population size with it.
    coarse = variance.decompose(records, account, config, floor_cents=10_000_000_00)

    assert len(coarse["drivers"]) == 1
    assert coarse["drivers"][0]["grouped"] >= 1
    assert coarse["drivers"][0]["amount_cents"] == coarse["actual_cents"]


def test_an_entry_no_event_claims_is_reported_not_absorbed(ws):
    """Absorbing it would attribute a movement to a transaction that did not cause it."""
    records = _records(ws)
    account = _biggest(records and ws)
    records.append({"role": "ledger", "record_key": "JE-ORPHAN\x1f1", "source_id": "s",
                    "locator": 1,
                    "payload": {"entry_id": "JE-ORPHAN", "line_id": "1",
                                "date": "2026-09-15", "account": account,
                                "debit_cents": 500_00, "credit_cents": 0}})

    result = variance.decompose(records, account, _config(ws))

    assert result["unexplained_cents"] == 500_00
    assert result["attributed_pct"] < 100
    # Still counted: the identity holds even when part of it cannot be traced.
    assert sum(d["amount_cents"] for d in result["drivers"]) == result["actual_cents"]


def test_attribution_is_floored_rather_than_rounded_up(ws):
    """Rounding up is how a gap comes to be described as complete."""
    records = _records(ws)
    account = _biggest(ws)
    actual = variance.decompose(records, account, _config(ws))["actual_cents"]
    # A residual of well under one percent of the account.
    records.append({"role": "ledger", "record_key": "JE-TINY\x1f1", "source_id": "s",
                    "locator": 1,
                    "payload": {"entry_id": "JE-TINY", "line_id": "1", "date": "2026-09-15",
                                "account": account, "debit_cents": max(1, actual // 500),
                                "credit_cents": 0}})

    result = variance.decompose(records, account, _config(ws))

    assert result["unexplained_cents"] > 0
    assert result["attributed_pct"] <= 99


# --------------------------------------------------------------------------- #
# Budget against actual
# --------------------------------------------------------------------------- #

def test_revenue_is_compared_in_the_direction_it_is_read(ws):
    """Revenue carries a credit balance. Comparing the raw movement with a positive
    budget would report every revenue line as an enormous shortfall."""
    records = _records(ws)
    rows = statements.balances(records)["accounts"]
    revenue = [r for r in rows.values() if r["type"] == "revenue" and r["movement_cents"]]
    assert revenue, "the fixture must have revenue for this to measure anything"

    for row in revenue:
        assert variance._actual(row) > 0


def test_an_account_with_activity_and_no_budget_is_named_not_dropped(ws):
    """Dropping it is how a variance report comes out clean while what it was meant to
    surface sits outside the join."""
    comparison = variance.budget_vs_actual(_records(ws), _config(ws))

    # The generated chart budgets expenses only, so revenue lands here.
    assert comparison["unplanned"], "the fixture must leave something unbudgeted"
    for item in comparison["unplanned"]:
        assert item["actual_cents"]
        assert "not the same as a variance of zero" in item["reason"]


def test_overspending_is_adverse_and_over_earning_is_not(ws):
    """The sign alone does not say whether a variance is good news."""
    lines = variance.budget_vs_actual(_records(ws), _config(ws))["lines"]
    expenses = [line for line in lines if line["type"] == "expense"]
    assert expenses

    for line in expenses:
        assert line["favourable"] == (line["variance_cents"] <= 0)


def test_variances_are_not_totalled_across_account_types(ws):
    """An expense overspend and a revenue shortfall are not the same quantity."""
    totals = variance.budget_vs_actual(_records(ws), _config(ws))["totals"]

    assert set(totals) == {"revenue", "expense"}
    assert "total" not in totals


def test_a_budget_line_carries_the_approval_that_set_it(ws):
    """The first question about a variance is who said the number it is measured against."""
    for line in variance.budget_vs_actual(_records(ws), _config(ws))["lines"]:
        assert line["authority"], line["account"]
        assert line["evidence"][0]["record_key"]


def test_the_same_machinery_measures_against_a_forecast(ws):
    against_forecast = variance.budget_vs_actual(_records(ws), _config(ws), plan="forecasts")

    assert against_forecast["lines"]
    assert all(line["authority"] for line in against_forecast["lines"])


def test_an_unknown_plan_is_refused_rather_than_guessed_at(ws):
    with pytest.raises(ValueError):
        variance.budget_vs_actual(_records(ws), _config(ws), plan="hopes")


# --------------------------------------------------------------------------- #
# What C3 reads
# --------------------------------------------------------------------------- #

def test_the_explanation_is_scored_by_its_weakest_line(ws):
    """An agent is only as traceable as its worst decomposition."""
    result = variance.explain(_records(ws), _config(ws))

    assert result["explained"]
    assert result["attributed_pct"] == min(e["attributed_pct"] for e in result["explained"])


def test_a_clean_period_attributes_everything_it_reports(ws):
    result = variance.explain(_records(ws), _config(ws))

    assert result["unexplained_cents"] == 0
    assert result["attributed_pct"] == 100


# --------------------------------------------------------------------------- #
# Roll-up, forecasting and scenarios
# --------------------------------------------------------------------------- #

def test_a_roll_up_uses_the_charts_own_categories(ws):
    """Inventing a second taxonomy is how two reports of one period stop agreeing."""
    records = _records(ws)
    result = planning.roll_up(records, _config(ws))
    mappings = {row["mapping"] for row in statements.balances(records)["accounts"].values()}

    assert result["categories"]
    for bucket in result["categories"]:
        assert bucket["category"] in mappings or bucket["category"] == "uncategorized"


def test_a_category_holding_unbudgeted_accounts_says_so(ws):
    result = planning.roll_up(_records(ws), _config(ws))
    partial = [c for c in result["categories"] if c["unplanned_accounts"]]

    assert partial, "the fixture leaves revenue unbudgeted, so this must find something"
    for bucket in partial:
        assert not bucket["fully_budgeted"]


def test_a_category_nothing_budgeted_has_no_variance_rather_than_one_of_its_own_size(ws):
    """Revenue is unbudgeted in this fixture. Reporting its whole actual as a variance
    would read as an overspend against a budget nobody ever set."""
    result = planning.roll_up(_records(ws), _config(ws))
    revenue = next(c for c in result["categories"] if c["type"] == "revenue")

    assert revenue["actual_cents"] > 0
    assert revenue["planned_cents"] == 0
    assert revenue["variance_cents"] is None


def test_a_partly_budgeted_category_is_measured_against_the_budgeted_part(ws):
    for bucket in planning.roll_up(_records(ws), _config(ws))["categories"]:
        assert bucket["budgeted_actual_cents"] + bucket["unplanned_actual_cents"] ==             bucket["actual_cents"]
        if bucket["variance_cents"] is not None:
            assert bucket["variance_cents"] ==                 bucket["budgeted_actual_cents"] - bucket["planned_cents"]


def test_a_per_head_figure_is_given_only_where_headcount_was_supplied(ws):
    result = planning.roll_up(_records(ws), _config(ws))

    assert result["headcount"]["total"] > 0
    assert "not a salary" in result["note"]
    for bucket in result["categories"]:
        if bucket["type"] == "revenue":
            assert bucket["cost_per_head_cents"] is None


def test_a_forecast_miss_is_measured_against_the_forecast(ws):
    """Dividing by the outcome answers a different question."""
    result = planning.forecast_accuracy(_records(ws), _config(ws))

    assert result["accounts"]
    for row in result["accounts"]:
        if row["miss_pct"] is not None and row["forecast_cents"]:
            assert row["miss_pct"] == abs(row["miss_cents"]) * 100 // abs(row["forecast_cents"])


def test_a_forecast_carries_the_basis_it_claimed_for_itself(ws):
    """A run-rate miss and a bottom-up miss are different facts."""
    for row in planning.forecast_accuracy(_records(ws), _config(ws))["accounts"]:
        assert row["basis"]


def test_a_scenario_is_labelled_a_projection_throughout(ws):
    result = planning.scenario(_records(ws), _config(ws), revenue_growth_pct=10, periods=3)

    assert result["measured"] is False
    assert len(result["projection"]) == 3
    assert "has not happened" in result["note"]
    assert result["assumptions"]["revenue_growth_pct"] == 10


def test_a_scenario_carries_the_measured_period_it_was_built_from(ws):
    records = _records(ws)
    result = planning.scenario(records, _config(ws), periods=1)

    assert result["basis"]["revenue_cents"] == statements.income_statement(records)["total_revenue_cents"]
    assert result["basis"]["source"]


def test_a_scenario_refuses_a_horizon_it_cannot_stand_behind(ws):
    with pytest.raises(ValueError):
        planning.scenario(_records(ws), _config(ws), periods=planning.MAX_HORIZON + 1)


def test_the_same_assumptions_give_the_same_projection(ws):
    """Integer arithmetic throughout, so a projection repeated is a projection reproduced."""
    records, config = _records(ws), _config(ws)
    arguments = {"revenue_growth_pct": 7, "expense_growth_pct": 3, "periods": 6}

    assert (planning.scenario(records, config, **arguments)["projection"]
            == planning.scenario(records, config, **arguments)["projection"])


# --------------------------------------------------------------------------- #
# The report C5 fills in
# --------------------------------------------------------------------------- #

def test_the_report_offers_prose_slots_and_no_figure_slots(ws):
    """"Writes prose, never numbers" is a property of the tool, not a line in a prompt."""
    report = reporting.management_report(_records(ws), _config(ws))

    assert report["sections"]
    for section in report["sections"]:
        assert section["intent"]
        for figure in section.get("figures", []):
            assert figure["amount_cents"] is not None
            assert figure["from"], figure["label"]


def test_every_figure_in_the_report_names_the_module_that_computed_it(ws):
    report = reporting.management_report(_records(ws), _config(ws))
    sources = {f["from"] for s in report["sections"] for f in s.get("figures", [])}

    assert sources
    assert all(source.split(".")[0] in ("statements", "variance", "planning")
               for source in sources), sources


def test_the_report_reproduces_the_statements_rather_than_recomputing_them(ws):
    """A board pack that disagrees with the statements is a board pack nobody can use."""
    records, config = _records(ws), _config(ws)
    report = reporting.management_report(records, config)
    income = statements.income_statement(records)
    result = next(s for s in report["sections"] if s["id"] == "result")

    assert {f["label"]: f["amount_cents"] for f in result["figures"]}["Result"] == \
        income["net_income_cents"]


def test_a_clean_period_produces_a_presentable_report(ws):
    report = reporting.management_report(_records(ws), _config(ws))

    assert report["problems"] == [], report["problems"]
    assert report["presentable"]
    assert all(report["ties"].values())


def test_a_report_over_figures_that_do_not_tie_is_built_and_marked(ws):
    """Refusing leaves nothing to work from; building silently puts an unreconciled
    figure in front of a board. Saying so is the honest third option."""
    records = _records(ws)
    records.append({"role": "ledger", "record_key": "JE-BAD\x1f1", "source_id": "s",
                    "locator": 1,
                    "payload": {"entry_id": "JE-BAD", "line_id": "1", "date": "2026-09-15",
                                "account": "6100", "debit_cents": 50_000, "credit_cents": 0}})

    report = reporting.management_report(records, _config(ws))

    assert not report["presentable"]
    assert report["problems"]
    assert "not to be presented" in report["note"]
