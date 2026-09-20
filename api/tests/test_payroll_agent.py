"""The Payroll & Budget specialist (role `py`).

No network: the model is stubbed so these test the agent's boundaries, not LLM
quality. The point of every case is the same — a conclusion only survives if the
agent actually retrieved what it cites and took its amount from the engine.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.model import ModelBudgetExceeded, SpecialistRefusal, StructuredSpecialistModel
from app.agents.payroll import DraftClaim, DraftFindings, EvidenceSelection, PayrollBudgetSpecialist
from app.cfo.demo import DemoData, ScriptedAuditor, ScriptedCFO, ScriptedSpecialist
from app.cfo.engine import CFOEngine
from app.cfo.repository import RunRepository
from app.cfo.schemas import Limits, Run, RunRequest, TaskSpec, TaskState
from app.cfo.tools import EvidenceTools

ALL_SOURCES = ["payroll", "award", "service"]


class StubModel:
    """Returns prepared structured responses in order, recording what it saw."""

    label = "stub/payroll"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.payloads = []
        self.calls = 0
        self.input_tokens = self.output_tokens = 0

    def reset(self):
        self.calls = 0

    async def generate(self, system, instruction, payload, schema):
        self.payloads.append(payload)
        self.calls += 1
        if not self.responses:
            raise SpecialistRefusal("No stubbed response remains.")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        assert isinstance(response, schema), f"stub returned {type(response)} for {schema}"
        return response


def selection(sources=ALL_SOURCES, calculations=("payroll-allocation",), focus="Check the allocation."):
    return EvidenceSelection(focus=focus, source_ids=list(sources), calculation_ids=list(calculations))


def claim(**overrides):
    draft = {"id": "payroll-reclass", "event_key": "PAY-104-allocation",
             "title": "Payroll fund allocation requires correction",
             "conclusion": "The recorded award charge exceeds the allocation supported by the current service record.",
             "disposition": "substantiated", "evidence_ids": list(ALL_SOURCES),
             "calculation_id": "payroll-allocation",
             "proposed_action": "Submit a balanced reclassification proposal to the authorized human reviewer."}
    return DraftClaim(**{**draft, **overrides})


def findings(*claims, summary="Reperformed the payroll allocation.", requests=()):
    return DraftFindings(summary=summary, claims=list(claims), evidence_requests=list(requests))


def run_task(model, *, sources=ALL_SOURCES, limits=None, feedback=None, data=None):
    """Drive one investigate() call through a real EvidenceTools gateway."""
    data = data or DemoData()
    request = RunRequest(limits=limits or Limits())
    run = Run(id="CFO-test", request=request)
    scope = asyncio.run(data.snapshot("sandbox"))
    run.scope = scope
    spec = TaskSpec(id="allocation", role="py", objective="Check payroll allocation against service evidence.",
                    source_ids=list(sources), success_criteria="Return a cited deterministic calculation or an evidence request.")
    task = TaskState(spec=spec)
    scoped = scope.model_copy(deep=True)
    scoped.sources = [s for s in scoped.sources if s.id in spec.source_ids]
    scoped.calculations = [c for c in scoped.calculations if set(c.source_ids).issubset(spec.source_ids)]
    events = []
    tools = EvidenceTools(data, scoped, run, task, "py", lambda *a, **k: events.append(a), spec.source_ids)
    agent = PayrollBudgetSpecialist(model)
    result = asyncio.run(agent.investigate(spec, scoped, tools, [], feedback))
    return result, tools, run


def test_supported_claim_keeps_its_calculation_and_cited_evidence():
    model = StubModel(selection(), findings(claim()))
    result, tools, run = run_task(model)
    assert len(result.claims) == 1
    only = result.claims[0]
    assert only.calculation_id == "payroll-allocation"
    assert set(only.evidence_ids) == set(ALL_SOURCES)
    # The agent really retrieved everything it cites, so the coordinator's check passes.
    assert tools.validate_claim(only) is not None
    assert run.tool_calls == 4


def test_claim_citing_unretrieved_evidence_is_withheld_not_forwarded():
    model = StubModel(selection(sources=["payroll"], calculations=()),
                      findings(claim(evidence_ids=["payroll", "service"], calculation_id=None, disposition="explained")))
    result, _, _ = run_task(model)
    # 'service' was never read, so it cannot be cited; the claim survives on what was.
    assert result.claims[0].evidence_ids == ["payroll"]


def test_claim_whose_every_citation_is_unretrieved_is_dropped_with_a_reason():
    model = StubModel(selection(sources=["payroll"], calculations=()),
                      findings(claim(evidence_ids=["service"], calculation_id=None, disposition="explained")))
    result, _, _ = run_task(model)
    assert result.claims == []
    assert any("cited no evidence retrieved" in r for r in result.evidence_requests)


def test_claim_naming_a_calculation_the_agent_never_ran_is_dropped():
    model = StubModel(selection(calculations=()), findings(claim()))
    result, _, _ = run_task(model)
    assert result.claims == []
    assert any("did not perform" in r for r in result.evidence_requests)


@pytest.mark.parametrize("prose", ["The award was overcharged by $4,000.00.", "Roughly 60% is unsupported.",
                                   "An excess of 1,000,000 cents was charged."])
def test_model_authored_amounts_never_reach_a_claim(prose):
    model = StubModel(selection(), findings(claim(conclusion=prose)))
    result, _, _ = run_task(model)
    assert result.claims == []
    assert any("amounts must come from the calculation engine" in r for r in result.evidence_requests)


def test_substantiated_findings_require_a_deterministic_amount():
    model = StubModel(selection(calculations=()), findings(claim(calculation_id=None)))
    result, _, _ = run_task(model)
    assert result.claims == []
    assert any("needs a deterministic calculation" in r for r in result.evidence_requests)


class CleanData(DemoData):
    """Same scope, but the engine finds no exception to substantiate."""

    async def calculate(self, scope, calculation_id):
        result = await super().calculate(scope, calculation_id)
        return result.model_copy(update={"amount_cents": 0, "category": "none"})


def test_a_calculation_that_found_no_exception_cannot_substantiate_one():
    model = StubModel(selection(), findings(claim()))
    result, _, _ = run_task(model, data=CleanData())
    # The engine, not the narrative, decides whether there is an exception.
    assert result.claims[0].disposition == "cleared"
    assert result.claims[0].calculation_id == "payroll-allocation"


def test_explained_findings_are_allowed_without_an_amount():
    model = StubModel(selection(calculations=()),
                      findings(claim(disposition="explained", calculation_id=None,
                                     conclusion="Allocation rests on the award clause requiring service evidence.")))
    result, _, _ = run_task(model)
    assert len(result.claims) == 1 and result.claims[0].calculation_id is None


def test_calculation_source_evidence_is_added_even_when_the_model_omits_it():
    model = StubModel(selection(), findings(claim(evidence_ids=["payroll"])))
    result, tools, _ = run_task(model)
    # validate_claim requires every calculation source among the cited evidence.
    assert set(result.claims[0].evidence_ids) == set(ALL_SOURCES)
    assert tools.validate_claim(result.claims[0]) is not None


def test_missing_service_evidence_becomes_a_request_not_a_finding():
    model = StubModel(selection(sources=["payroll", "award"], calculations=()),
                      findings(summary="No current service record is available.",
                               requests=["Provide the current payroll service record; a budget split is insufficient."]))
    result, _, _ = run_task(model, sources=["payroll", "award"], data=DemoData(missing_service=True))
    assert result.claims == []
    assert "service record" in result.evidence_requests[0]


def test_a_small_evidence_budget_is_planned_within_and_reported():
    model = StubModel(selection(), findings(claim(evidence_ids=["payroll"], calculation_id=None, disposition="explained")))
    result, _, run = run_task(model, limits=Limits(tool_calls_per_agent_task=1))
    # It trims its own plan rather than spending past the allowance, and says so.
    assert run.tool_calls == 1
    assert any("did not cover everything" in r for r in result.evidence_requests)
    assert result.claims and result.claims[0].evidence_ids == ["payroll"]


def test_the_first_attempt_keeps_evidence_budget_back_for_a_retry():
    model = StubModel(selection(), findings(claim()))
    _, _, run = run_task(model, limits=Limits(tool_calls_per_agent_task=6))
    # 70% of six leaves room for the targeted read a challenge would need.
    assert run.tool_calls == 4


def test_a_retry_after_a_challenge_may_use_the_whole_remaining_budget():
    """The same task and selection reaches further once it is answering the auditor."""
    limits = Limits(tool_calls_per_agent_task=5)
    _, _, first = run_task(StubModel(selection(), findings(claim())), limits=limits)
    _, _, retry = run_task(StubModel(selection(), findings(claim())), limits=limits,
                           feedback="payroll-reclass: cite the service record.")
    assert first.tool_calls == 2 < retry.tool_calls == 4


def test_unknown_source_and_calculation_ids_from_the_model_are_ignored():
    model = StubModel(selection(sources=["payroll", "other-school"], calculations=("invented",)),
                      findings(claim(evidence_ids=["payroll"], calculation_id=None, disposition="explained")))
    result, _, run = run_task(model, sources=["payroll"])
    assert run.tool_calls == 1
    assert result.claims[0].evidence_ids == ["payroll"]


def test_a_task_with_no_delegated_sources_asks_for_scope():
    model = StubModel()
    result, _, run = run_task(model, sources=[])
    assert result.claims == [] and run.tool_calls == 0
    assert "Delegate payroll" in result.evidence_requests[0]


@pytest.mark.parametrize("failure", [SpecialistRefusal("refused"), ModelBudgetExceeded("spent")])
def test_model_failure_fails_closed_with_no_claims(failure):
    result, _, _ = run_task(StubModel(failure))
    assert result.claims == [] and result.evidence_requests


def test_findings_step_failure_keeps_retrieved_evidence_but_claims_nothing():
    result, _, run = run_task(StubModel(selection(), SpecialistRefusal("truncated")))
    assert result.claims == [] and run.tool_calls == 4
    assert "no reviewable conclusion was produced" in result.summary


def test_auditor_feedback_reaches_both_model_steps():
    model = StubModel(selection(), findings(claim()))
    run_task(model, feedback="payroll-reclass: cite the service record. CFO: retry.")
    assert all(p["auditor_feedback"].startswith("payroll-reclass") for p in model.payloads)


def test_duplicate_claim_identifiers_are_withheld():
    model = StubModel(selection(), findings(claim(), claim(event_key="other")))
    result, _, _ = run_task(model)
    assert len(result.claims) == 1
    assert any("duplicate claim identifier" in r for r in result.evidence_requests)


def test_the_agent_runs_inside_the_real_coordinator_and_survives_independent_review(tmp_path):
    """End to end: planner delegates `py`, the agent works, the auditor reperforms."""
    model = StubModel(selection(), findings(claim()))
    repository = RunRepository(tmp_path / "runs.sqlite3")
    engine = CFOEngine(DemoData(), {"ap": ScriptedSpecialist(), "gr": ScriptedSpecialist(),
                                    "py": PayrollBudgetSpecialist(model)},
                       ScriptedAuditor(), ScriptedCFO(), repository)
    run = asyncio.run(engine.execute(engine.create(RunRequest())))
    assert run.status == "completed"
    payroll = next(a for a in run.accepted if a.role == "py")
    assert payroll.claim.id == "payroll-reclass"
    assert payroll.calculation.amount_cents == 400_000
    assert payroll.calculation.cash_delta_cents == 0
    assert payroll.review.verdict == "accept"
    assert "$4,000.00" in run.report_markdown


def test_specialist_model_uses_structured_output_and_enforces_its_own_budget():
    parsed = EvidenceSelection(focus="Check.", source_ids=["payroll"], calculation_ids=[])
    parse = AsyncMock(return_value=SimpleNamespace(output_parsed=parsed,
                                                   usage=SimpleNamespace(input_tokens=30, output_tokens=8)))
    model = StructuredSpecialistModel("openai", "test-model", SimpleNamespace(responses=SimpleNamespace(parse=parse)), max_calls=1)
    result = asyncio.run(model.generate("system", "instruction", {"a": 1}, EvidenceSelection))
    assert result == parsed
    assert parse.call_args.kwargs["store"] is False
    assert parse.call_args.kwargs["max_output_tokens"] == 2048
    assert model.input_tokens == 30
    with pytest.raises(ModelBudgetExceeded):
        asyncio.run(model.generate("system", "instruction", {"a": 1}, EvidenceSelection))
    model.reset()
    assert asyncio.run(model.generate("system", "instruction", {"a": 1}, EvidenceSelection)) == parsed


def test_specialist_model_never_forwards_the_hosted_key_to_a_local_host(monkeypatch):
    import openai

    clients = []
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kwargs: clients.append(kwargs) or SimpleNamespace())
    monkeypatch.setenv("SPECIALIST_PROVIDER", "local")
    monkeypatch.setenv("SPECIALIST_MODEL", "local-qwen-test")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-must-not-be-forwarded")
    monkeypatch.setenv("SPECIALIST_LOCAL_BASE_URL", "http://127.0.0.1:11434/v1")
    StructuredSpecialistModel.from_env()
    assert clients[0]["api_key"] == "local-unused"
    monkeypatch.setenv("SPECIALIST_LOCAL_BASE_URL", "https://untrusted.example/v1")
    with pytest.raises(ValueError):
        StructuredSpecialistModel.from_env()


def test_specialist_settings_fall_back_to_the_coordinator_configuration(monkeypatch):
    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kwargs: SimpleNamespace())
    monkeypatch.delenv("SPECIALIST_PROVIDER", raising=False)
    monkeypatch.delenv("SPECIALIST_MODEL", raising=False)
    monkeypatch.setenv("CFO_PROVIDER", "openai")
    monkeypatch.setenv("CFO_MODEL", "shared-model-id")
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    assert StructuredSpecialistModel.from_env().label == "openai/shared-model-id"
    monkeypatch.delenv("CFO_MODEL")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert StructuredSpecialistModel.from_env().model == "gpt-5.4-mini"
