from copy import deepcopy
import pytest
from app.accounting import receivables
from app.agents import runtime, schemas
from app.agents.registry import AGENTS
from app.agents.tools import Toolbox, ScopeError, dispatch, tool_definitions
from app.agents.budget import Meter

CONFIG = {"start": "2026-09-01", "end": "2026-09-30", "currency": "USD"}


def row(role, key, **payload):
    return {"role": role, "record_key": key, "source_id": "source-"+key, "locator": 2, "payload": payload}


def invoice(key="I", **overrides):
    return row("customer_invoices", key, **({"customer_id": "C", "currency": "USD", "invoice_number": "INV",
        "invoice_date": "2026-07-01", "due_date": "2026-08-31", "amount_cents": 10000} | overrides))


def receipt(key="R", **overrides):
    return row("remittances", key, **({"customer_id": "C", "currency": "USD", "reference": key,
        "invoice_refs": "INV", "received_date": "2026-09-01", "amount_cents": 4000} | overrides))


def test_partial_payment_ages_only_outstanding_and_preserves_inputs():
    records = [invoice(), receipt()]
    before = deepcopy(records)
    result = receivables.age_receivables(records, CONFIG)
    assert result["outstanding_cents"] == 6000
    assert result["buckets_cents"]["1-30"] == 6000
    assert result["received_cents"] == result["applied_cents"] + result["unapplied_cents"]
    assert result["exceptions"][0]["code"] == "partial_payment"
    assert records == before


@pytest.mark.parametrize("change", [{"customer_id": "OTHER"}, {"currency": "CAD"},
                                    {"invoice_refs": "INV,OTHER"}, {"invoice_refs": ""}])
def test_no_guessed_allocation(change):
    result = receivables.match_remittances([invoice(), receipt(**change)], CONFIG)
    assert result["applied_cents"] == 0
    assert result["unapplied_cents"] == 4000


def test_duplicate_invoice_numbers_and_receipts_are_not_double_applied():
    for records in ([invoice(), invoice("I2"), receipt()],
                    [invoice(), receipt(), receipt("R2", reference="R")]):
        result = receivables.match_remittances(records, CONFIG)
        assert result["applied_cents"] == 0
        assert result["unapplied_cents"] == result["received_cents"]


def test_overpayment_is_not_netted_against_another_invoice():
    result = receivables.age_receivables([invoice(), invoice("I2", invoice_number="OTHER"), receipt(amount_cents=15000)], CONFIG)
    assert result["unapplied_cents"] == 5000
    assert result["outstanding_cents"] == 10000


def test_later_receipts_do_not_change_historical_aging():
    result = receivables.age_receivables([invoice(), receipt(received_date="2026-10-01")], CONFIG)
    assert result["outstanding_cents"] == 10000
    with pytest.raises(ValueError):
        receivables.age_receivables([], CONFIG, "2026-10-01")


@pytest.mark.parametrize("days,bucket", [(0,"current"),(1,"1-30"),(30,"1-30"),(31,"31-60"),(60,"31-60"),(61,"61-90"),(90,"61-90"),(91,"over-90")])
def test_aging_boundaries(days, bucket):
    from datetime import date, timedelta
    due = (date(2026,9,30)-timedelta(days=days)).isoformat()
    result = receivables.age_receivables([invoice(invoice_date="2026-01-01", due_date=due)], CONFIG)
    assert result["buckets_cents"][bucket] == 10000


def test_tools_enforce_scope_record_citations_and_escalate_engine_results():
    box = Toolbox("ws", AGENTS["A2"], Meter(), [invoice(), receipt()], CONFIG, "snap", "thread")
    assert {"age_receivables", "match_remittance"} <= {t["name"] for t in tool_definitions(AGENTS["A2"])}
    result = dispatch(box, "age_receivables", {})
    box.validate_citations([schemas.Citation(**c) for c in result["applications"][0]["citations"]])
    assert "partial_payment" in runtime.engine_exceptions(box.calculations)
    with pytest.raises(ScopeError):
        dispatch(Toolbox("ws", AGENTS["B3"], Meter(), [], CONFIG, "s", "t"), "age_receivables", {})


def test_every_specialist_tool_is_exposed_or_owned_by_the_graph():
    for spec in AGENTS.values():
        if spec.tier == "subagent":
            assert set(spec.tools) - {"delegate"} <= {t["name"] for t in tool_definitions(spec)}, spec.id
