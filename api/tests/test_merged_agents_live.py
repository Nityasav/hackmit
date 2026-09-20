"""Billable developer smoke test for the payroll specialist against real intake.

Not a five-agent integration or a blind issue-detection benchmark.
"""
import asyncio
import json
import os
from pathlib import Path

import pytest

from app.agents.payroll import PayrollBudgetSpecialist
from app.cfo.schemas import Limits, Run, RunRequest, TaskSpec, TaskState
from app.cfo.tools import EvidenceTools
from app.integrations.cfo_intake import IntakeDataSource
from .test_cfo_agent import HEADERS, committed_workspace

pytestmark = pytest.mark.skipif(os.getenv("SCHOOLTRACE_LIVE_EVAL") != "1", reason="Opt-in billable merged-agent evaluation")


def save(name, report):
    output = Path(os.environ["SCHOOLTRACE_EVAL_OUTPUT"])
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{name}.json").write_text(json.dumps(report, indent=2))


def test_live_payroll_on_isolated_intake(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOOLTRACE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SPECIALIST_MODEL", os.getenv("OPENAI_MODEL", "gpt-5.4-mini"))
    monkeypatch.setenv("SPECIALIST_PROVIDER", "openai")
    with TestClient(app, headers=HEADERS) as client:
        ws, _ = committed_workspace(client)
        async def investigate():
            data = IntakeDataSource()
            scope = await data.snapshot(ws)
            ids = [s.id for s in scope.sources if s.domain in {"py", "gr", "shared"}]
            scoped = scope.model_copy(deep=True)
            scoped.sources = [s for s in scope.sources if s.id in ids]
            scoped.calculations = [c for c in scope.calculations if set(c.source_ids).issubset(ids)]
            spec = TaskSpec(id="eval-payroll", role="py", objective="Tie out payroll and determine whether the supplied evidence supports award allocation.",
                            source_ids=ids, success_criteria="Use deterministic amounts or request missing support.")
            run = Run(id="eval", request=RunRequest(workspace=ws, mode="live", limits=Limits()))
            run.scope = scope
            task = TaskState(spec=spec)
            events = []
            tools = EvidenceTools(data, scoped, run, task, "py", lambda *a, **k: events.append(a), ids)
            agent = PayrollBudgetSpecialist.from_env()
            started = time.monotonic()
            try:
                result = await agent.investigate(spec, scoped, tools, [], None)
                save("payroll", {"kind": "development_not_held_out", "model": agent.label,
                    "seconds": round(time.monotonic() - started, 3), "model_calls": agent.model.calls,
                    "input_tokens": agent.model.input_tokens, "output_tokens": agent.model.output_tokens,
                    "tool_calls": run.tool_calls, "result": result.model_dump(), "events": events})
                assert agent.model.calls == 2 and run.tool_calls > 0
                assert result.claims or result.evidence_requests
                for claim in result.claims:
                    tools.validate_claim(claim)
            finally:
                await agent.model.close()
        asyncio.run(investigate())
