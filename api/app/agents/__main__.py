"""Run the Payroll & Budget agent against one committed workspace snapshot.

A full live CFO run needs AP, Grants and the independent Internal Auditor as
well, so this entry point exercises the `py` agent on its own: real intake
records, the real evidence gateway with real budgets, the real accounting
engine, and a real structured-output model call.

    uv run --extra cfo python -m app.agents ws-0123456789abcdef

Nothing is approved, posted or written back. Claims printed here have NOT been
through independent review, which is the gate that would make them reportable.
"""

import argparse
import asyncio
import json

from ..cfo.schemas import Limits, Run, RunRequest, TaskSpec, TaskState
from ..cfo.tools import EvidenceTools
from ..integrations.cfo_intake import IntakeDataSource
from .payroll import PayrollBudgetSpecialist

OBJECTIVE = ("Tie out payroll for the period and test the fund allocations, using the "
             "deterministic calculations published for this snapshot.")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", help="Intake workspace ID with a committed snapshot")
    parser.add_argument("--objective", default=OBJECTIVE)
    parser.add_argument("--tool-calls", type=int, default=12, help="Evidence tool budget for the task")
    args = parser.parse_args()

    data = IntakeDataSource()
    scope = await data.snapshot(args.workspace)
    # Payroll needs its own records plus the award and ledger context they are tested against.
    delegated = [s.id for s in scope.sources if s.domain in {"py", "gr", "shared"}]
    if not delegated:
        print("This snapshot exposes no payroll, grant or shared sources.")
        return 1

    scoped = scope.model_copy(deep=True)
    scoped.sources = [s for s in scoped.sources if s.id in delegated]
    scoped.calculations = [c for c in scoped.calculations if set(c.source_ids).issubset(delegated)]
    print(f"{scope.institution} — {scope.period}")
    print(f"Snapshot {scope.snapshot_id}: {len(scoped.sources)} sources, {len(scoped.calculations)} deterministic calculations\n")

    spec = TaskSpec(id="payroll-tieout", role="py", objective=args.objective, source_ids=delegated,
                    success_criteria="Cite retrieved evidence and a deterministic calculation, or request the missing record.")
    run = Run(id="PAYROLL-CLI", request=RunRequest(workspace=args.workspace, mode="live",
                                                   limits=Limits(tool_calls_per_agent_task=args.tool_calls)))
    run.scope = scope
    task = TaskState(spec=spec)

    def emit(actor, action, detail, task_id=None, references=None):
        print(f"  [{actor}] {action}: {detail[:160]}")

    agent = PayrollBudgetSpecialist.from_env()
    print(f"Specialist model: {agent.label}\n")
    tools = EvidenceTools(data, scoped, run, task, "py", emit, delegated)
    try:
        result = await agent.investigate(spec, scoped, tools, [], None)
    finally:
        await agent.model.close()

    print("\n" + json.dumps(result.model_dump(), indent=2))
    print(f"\nEvidence tool calls: {run.tool_calls}; specialist model calls: {agent.model.calls}; "
          f"tokens: {agent.model.input_tokens} in / {agent.model.output_tokens} out")
    print("These conclusions have not been independently reviewed and are not approved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
