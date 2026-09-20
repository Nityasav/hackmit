"""Billable developer smoke tests for the merged AP and payroll implementations.

No existing workspaces are touched; AP writes live only in this test process.
These are not a five-agent integration or blind issue-detection benchmark.
"""
import asyncio
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from openai import OpenAI

from app.main import app
from app import store
from app.agents import run_loop
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


def test_live_cfo_ap_auditor_handoff(monkeypatch):
    store.reset()
    initial = store.get_bundle("sandbox")
    old_findings = {f.id for f in initial.findings}
    old_tasks = {t.id for t in initial.tasks}
    old_decisions = {d.id for d in initial.decisions}
    model = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("AP_MODEL", model)
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "requests": 0}
    started = time.monotonic()
    with OpenAI(timeout=60, max_retries=0, base_url="https://api.openai.com/v1") as real:
        def create(**kwargs):
            response = real.responses.create(**kwargs)
            usage["requests"] += 1
            if response.usage:
                for key in ("input_tokens", "output_tokens", "total_tokens"):
                    usage[key] += getattr(response.usage, key, 0)
            return response
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        try:
            result = run_loop.run_cfo_agent(
                "Investigate whether INV-2302 should enter a payment batch. Delegate to AP to inspect the "
                "original records and file one evidence-backed finding, then delegate that exact new finding "
                "to Internal Auditor to reread the originals and submit its review. Finally write a limited "
                "briefing. Do not release or approve payments; do not infer fraud.",
                client=client, budget=6, specialist_budget=12, max_turns=12)
            bundle = store.get_bundle("sandbox")
            tasks = [t for t in bundle.tasks if t.id not in old_tasks]
            findings = [f for f in bundle.findings if f.id not in old_findings]
            decisions = [d for d in bundle.decisions if d.id not in old_decisions]
            report = {"kind": "development_fixture_not_held_out", "model": model, "usage": usage,
                      "seconds": round(time.monotonic() - started, 3), "answer": result.answer,
                      "stop_reason": result.stop_reason, "cfo_tools": result.tool_calls,
                      "tasks": [t.model_dump() for t in tasks], "findings": [f.model_dump() for f in findings],
                      "decisions": [d.model_dump() for d in decisions]}
            save("cfo_ap_auditor", report)
            assert result.stop_reason == "completed"
            assert {t.agent for t in tasks} >= {"ap", "au"}
            assert findings and any(f.verified_by == "au" for f in findings)
            assert all(t.column != "working" for t in tasks)
            assert any(d.agent == "ap" for d in decisions) and any(d.agent == "au" for d in decisions)
            assert all(a.status == before.status for a, before in zip(bundle.approvals, initial.approvals))
        finally:
            store.reset()


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
