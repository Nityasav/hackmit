"""Cache the public vals-ai/finance_agent_benchmark rows for the abstention benchmark.

    uv run python scripts/fetch_finance_benchmark.py

Reads the Hugging Face datasets-server REST API through `httpx`, which this
project already depends on, so no `datasets`/`torch` stack enters the
environment for a 50-row, 50KB file. The written file
carries its own provenance: tests refuse to run against a cache whose
recorded digest does not match its rows, so a hand-edited benchmark cannot
quietly become the thing a score is reported against.

Dataset: vals-ai/finance_agent_benchmark, licensed CC-BY-4.0. These are the
50 publicly previewed rows of a 537-question benchmark; attribution is
required wherever a score derived from them is published.
"""

import hashlib
import json
from datetime import date
from pathlib import Path

import httpx

DATASET = "vals-ai/finance_agent_benchmark"
ENDPOINT = "https://datasets-server.huggingface.co/rows"
DESTINATION = Path(__file__).resolve().parents[1] / "tests" / "data" / "finance_agent_benchmark.json"
COLUMNS = ["Question", "Answer", "Question Type", "Expert time (mins)", "Rubric"]


def digest(rows: list[dict]) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def fetch() -> list[dict]:
    rows, offset = [], 0
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        while True:
            response = client.get(ENDPOINT, params={
                "dataset": DATASET, "config": "default", "split": "train",
                "offset": offset, "length": 100})
            response.raise_for_status()
            page = response.json()
            batch = [item["row"] for item in page["rows"]]
            rows.extend(batch)
            offset += len(batch)
            if not batch or offset >= page.get("num_rows_total", offset):
                break
    return rows


def main() -> None:
    rows = fetch()
    missing = {column for row in rows for column in COLUMNS if column not in row}
    if missing:
        raise SystemExit(f"Upstream schema changed; columns absent: {sorted(missing)}")
    payload = {
        "dataset": DATASET,
        "source": f"https://huggingface.co/datasets/{DATASET}",
        "license": "cc-by-4.0",
        "retrieved": date.today().isoformat(),
        "note": "Public 50-row preview of a 537-question benchmark. Treat scores as a floor: "
                "these rows are the most likely to appear in model training data.",
        "sha256": digest(rows),
        "rows": rows,
    }
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    DESTINATION.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(rows)} rows -> {DESTINATION}")
    print(f"sha256 {payload['sha256']}")


if __name__ == "__main__":
    main()
