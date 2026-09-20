#!/usr/bin/env python
"""Run the AP & Payments agent's AR extension against a real benchmark workspace
(https://github.com/ciru-ai/invoice-sandbox-benchmark) and write a scoreable
submission.csv.

Usage:
    uv run python scripts/run_ar_benchmark.py /path/to/runs/test-001/workspace [output.csv]

Then, from the benchmark repo itself:
    python scripts/score_submission.py /path/to/output.csv

Reads OPENAI_API_KEY from api/.env (gitignored) or the environment. Makes a
real, billed API call — this is not part of the test suite. ~112 invoices at
the default budget takes several minutes and a few dollars; the mixed-trap
subset this was validated against (9 files, every trap type) is far cheaper
if you just want to sanity-check the pipeline again.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.agents.ar_reconciliation import (  # noqa: E402
    reduce_to_customer_totals,
    run_ar_reconciliation,
    write_submission_csv,
)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_ar_benchmark.py <workspace_dir> [output.csv]")
        raise SystemExit(1)

    workspace_dir = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "submission.csv"

    print(f"Workspace: {workspace_dir}")
    result, ledger = run_ar_reconciliation(workspace_dir)

    print("\n=== Answer ===")
    print(result.answer or "(no final answer text — see stop reason below)")
    print(f"\nStop reason: {result.stop_reason}")
    print(f"Tool calls used: {result.tool_calls_used}/{result.tool_budget}")
    print(f"Documents classified: {len(ledger)}")

    by_type: dict[str, int] = {}
    for entry in ledger:
        by_type[entry.document_type] = by_type.get(entry.document_type, 0) + 1
    for doc_type, count in sorted(by_type.items()):
        print(f"  {doc_type}: {count}")

    totals = reduce_to_customer_totals(ledger)
    path = write_submission_csv(totals, output_path)
    print(f"\nWrote {len(totals)} customer totals to {path}")
    print(f"\nScore it from the benchmark repo with:\n  python scripts/score_submission.py {path}")


if __name__ == "__main__":
    main()
