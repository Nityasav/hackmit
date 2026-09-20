"""Run an explicitly scripted CFO integration demo without API credentials."""

import argparse
import asyncio
from pathlib import Path

from .demo import DemoData, ScriptedAuditor, ScriptedCFO, ScriptedSpecialist
from .engine import CFOEngine
from .repository import RunRepository
from .schemas import RunRequest


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--award-share", type=int, default=60)
    parser.add_argument("--missing-service", action="store_true")
    parser.add_argument("--db", default=str(Path(".venv") / "cfo-demo.sqlite3"))
    args = parser.parse_args()
    repository = RunRepository(args.db)
    engine = CFOEngine(DemoData(args.award_share, args.missing_service),
                       {role: ScriptedSpecialist() for role in ["ap", "py", "gr"]},
                       ScriptedAuditor(), ScriptedCFO(), repository)
    run = await engine.execute(engine.create(RunRequest()))
    print(run.report_markdown)


if __name__ == "__main__":
    asyncio.run(main())
