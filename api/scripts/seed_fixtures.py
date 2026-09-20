"""Regenerate a recorded fixture by running the real pipeline over the sample pack.

`contracts/fixtures/sandbox.json` used to be authored by hand: fifteen tasks, four
findings and a before/after table that no code produced. This script replaces that
with a recording. It creates a workspace, commits the sample pack, runs the
five-agent coordinator over the committed snapshot, and writes whatever the
projection layer builds from the result.

    uv run python scripts/seed_fixtures.py             # offline, no API key, no cost
    uv run python scripts/seed_fixtures.py --live      # real model calls, real money

Offline is the default and is what the committed fixture is built from. In offline
mode the *prose* is stubbed -- a specialist's summary and an auditor's rationale are
written by the stub below -- but everything that matters is real: the records are
parsed and committed by `ingestion`, the amounts come from `app/accounting/`, the
auditor's independent re-read and reperformance run for real, and the bundle is
built by `app/projection.py`. The recording says which mode produced it in
`workspace.recorded_from`, so nobody has to guess.

`mit.json` is not regenerated. Its source is a published PDF hosted elsewhere, and
PDF extraction is not implemented, so there is nothing here to run agents over.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIXTURES = ROOT.parent / "contracts" / "fixtures"
PACK = json.loads((FIXTURES / "intake.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Offline stubs: prose only. Every amount still comes from the engine.
# --------------------------------------------------------------------------- #

class StubCFO:
    """Plans one task per specialist and writes no numbers."""

    label = "offline-stub"
    input_tokens = output_tokens = 0

    async def plan(self, objective, scope):
        from app.cfo.schemas import Plan, TaskSpec
        by_domain = {}
        for source in scope.sources:
            by_domain.setdefault(source.domain, []).append(source.id)
        shared = by_domain.get("shared", [])
        return Plan(
            rationale="Split the close by domain so each specialist reads only what it is "
                      "responsible for, and the auditor re-reads every cited original.",
            tasks=[TaskSpec(id=role, role=role,
                            objective=f"Review the {role} evidence in this snapshot and test it against "
                                      "the award terms and the deterministic calculations published for it.",
                            source_ids=(by_domain.get(role, []) + shared)[:4],
                            success_criteria="Cite retrieved originals and a published calculation, or "
                                             "state what is missing.")
                   for role in ("ap", "py", "gr") if by_domain.get(role) or shared])

    async def follow_up(self, task, claim, review):
        from app.cfo.schemas import FollowUp
        return FollowUp(action="stop", instruction="Recorded fixture does not retry a challenged claim.")

    async def synthesize(self, run):
        from app.cfo.schemas import Narrative, NarrativeItem
        return Narrative(items=[NarrativeItem(
            claim_id=item.claim.id,
            explanation="Reviewed against the cited originals and the published calculation.",
            proposed_next_step="Decide how to resolve this before the close is finalised.")
            for item in run.accepted])


class StubSpecialistModel:
    """Chooses real evidence and cites real calculation IDs; invents no amounts."""

    label = "offline-stub"
    calls = input_tokens = output_tokens = 0

    def __init__(self, **_):
        pass

    def reset(self):
        pass

    async def generate(self, system, instruction, payload, schema):
        from app.agents.payroll import DraftClaim, DraftFindings, EvidenceSelection
        from app.cfo.schemas import Review

        if schema is EvidenceSelection:
            return EvidenceSelection(
                focus="Read the originals, then reperform every calculation they support.",
                source_ids=[s["id"] for s in payload["sources"]],
                calculation_ids=[c["id"] for c in payload.get("calculations", [])])

        if schema is DraftFindings:
            task_id = payload["task"]["id"]
            evidence = [e["source_id"] for e in payload["evidence"]]
            # Only a calculation with a nonzero amount supports a substantiated claim.
            priced = next((c for c in payload["calculations"]
                           if c["amount_cents"] and c["category"] != "none"), None)
            if not priced:
                return DraftFindings(
                    summary="The evidence was read and every published calculation reperformed; "
                            "nothing in this domain is unsupported.",
                    evidence_requests=[], claims=[])
            # A claim may only cite sources this agent actually retrieved.
            cited = [s for s in priced["requires_evidence"] if s in evidence] or evidence[:1]
            return DraftFindings(
                summary="Reperformed the published calculations against the retrieved originals.",
                evidence_requests=[],
                claims=[DraftClaim(
                    id=f"{task_id}-1", event_key=priced["id"], title=priced["description"][:120],
                    conclusion="The calculation reperforms against the cited originals and is not "
                               "supported by any further record in this snapshot.",
                    disposition="substantiated", evidence_ids=cited,
                    calculation_id=priced["id"],
                    proposed_action="Resolve before the close is finalised.")])

        assert schema is Review
        return Review(verdict="accept",
                      rationale="Re-read the cited originals and reperformed the calculation; both agree.",
                      required_action="")

    async def close(self):
        pass


# --------------------------------------------------------------------------- #
# Running the pipeline
# --------------------------------------------------------------------------- #

def commit_pack(name: str) -> str:
    """Create a workspace and commit every non-deferred file in the sample pack."""
    from app import ingestion

    workspace = ingestion.create_workspace(ingestion.WorkspaceCreate(
        name=name, kind="synthetic", start=date.fromisoformat(PACK["start"]),
        end=date.fromisoformat(PACK["end"]), scope="Recorded September close"))
    ws = workspace["id"]
    files = [f for f in PACK["files"] if not f.get("later")]
    batch = ingestion.stage(ws, [(f["name"], f["content"].encode("utf-8"),
                                  ingestion.FileOptions(role=f["role"])) for f in files])
    saved = ingestion.commit(ws, batch["id"], ingestion.CommitRequest(
        expected_version=batch["version"], idempotency_key=batch["id"]))
    print(f"  committed {saved['counts']['new_records']} record(s) from {len(files)} file(s)")
    return ws


async def investigate(ws: str, live: bool):
    from app.cfo.engine import CFOEngine
    from app.cfo.repository import RunRepository
    from app.cfo.schemas import RunRequest
    from app.integrations.cfo_factory import create_adapters

    adapters = create_adapters()
    if live:
        from app.cfo.model import StructuredCFOModel
        model = StructuredCFOModel.from_env()
    else:
        from app.agents import model as specialist_model
        specialist_model.StructuredSpecialistModel.from_env = staticmethod(
            lambda **kwargs: StubSpecialistModel(**kwargs))
        model = StubCFO()

    engine = CFOEngine(adapters.data, adapters.specialists, adapters.auditor, model, RunRepository())
    run = engine.create(RunRequest(
        workspace=ws, mode="live", workflow="five_agent",
        objective="Review the September close, test every published calculation against the "
                  "originals behind it, and prepare a CFO briefing."))
    run = await engine.execute(run)
    print(f"  run {run.id}: {run.status}; {len(run.accepted)} accepted claim(s), "
          f"{len(run.unresolved)} unresolved")
    if hasattr(model, "close"):
        await model.close()
    return run


def record(ws: str, run, live: bool, out: Path, workspace_id: str, display_name: str):
    from app import projection

    bundle = projection.bundle(ws).model_dump(mode="json")
    stamp = f"run {run.id} on {date.today().isoformat()}, model {run.model_label}"
    bundle["workspace"].update({
        "id": workspace_id,
        "name": display_name,
        "mode": "recorded",
        "intake": False,
        "recorded_from": stamp + ("" if live else " (prose stubbed offline; amounts from the engine)"),
    })

    # Playbooks and the ablation belong to the Learning workstream, and this pipeline
    # does not produce them. Blanking them here would take that tab away from whoever
    # is building it, so a regeneration carries whatever the previous recording held.
    if out.exists():
        previous = json.loads(out.read_text(encoding="utf-8"))
        for key in ("playbooks", "ablation"):
            if previous.get(key):
                bundle[key] = previous[key]
        if bundle["playbooks"] and "learning" in bundle["workspace"]["disabled_tabs"]:
            bundle["workspace"]["disabled_tabs"].remove("learning")
    out.write_text(json.dumps(bundle, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    counts = {key: len(bundle[key]) for key in
              ("agents", "kpis", "workflows", "tasks", "findings", "approvals", "decisions")}
    print(f"  wrote {out.relative_to(ROOT.parent)}: {counts}")
    print(f"  provenance: {stamp}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true",
                        help="use the configured model instead of the offline stub (costs money)")
    parser.add_argument("--out", default=str(FIXTURES / "sandbox.json"))
    parser.add_argument("--workspace-id", default="sandbox")
    parser.add_argument("--name", default="Sandbox University")
    args = parser.parse_args()

    if args.live and not os.getenv("OPENAI_API_KEY"):
        print("--live needs OPENAI_API_KEY; put it in api/.env or the environment.")
        return 1
    if not args.live:
        # The factory only registers specialists when a provider looks configured.
        os.environ.setdefault("OPENAI_API_KEY", "offline-stub-not-sent")

    # Record into a scratch database so a regeneration never touches local intake data.
    with tempfile.TemporaryDirectory(prefix="schooltrace-seed-") as scratch:
        os.environ["SCHOOLTRACE_DATA_DIR"] = scratch
        print(f"{'LIVE' if args.live else 'OFFLINE'} recording into {scratch}")
        ws = commit_pack(args.name)
        run = asyncio.run(investigate(ws, args.live))
        record(ws, run, args.live, Path(args.out), args.workspace_id, args.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
