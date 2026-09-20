# SchoolTrace API

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000   # http://localhost:8000/docs
uv run pytest                                       # accounting invariants
```

## Layout

| Path | Owner | What goes here |
| --- | --- | --- |
| `app/main.py` | Functionality | HTTP endpoints (see `contracts/README.md`) |
| `app/models.py` | Functionality | Pydantic mirror of the bundle contract |
| `app/store.py` | Functionality | Fixed legacy demo bundles; new intake workspaces use the SQLite bundle builder |
| `app/db.py` | Functionality | SQLite schema, transactions, original bytes and local events |
| `app/ingestion.py` | Functionality | CSV/text parsing, mappings, validation, immutable commits, coverage and evidence requests |
| `app/accounting/` | Functionality | Exact integer-cent math and ledger invariants L01–L13 |
| `app/agents/` | Agent design | Model adapter, tool gateway, role prompts, orchestrator |
| `app/workflows/` | Workflows | Workflow definitions, demo scenarios, synthetic fixtures |

## Rules

- **Money is integer cents.** Never float. `app/accounting/money.py` owns parsing/allocation helpers; ingestion sums integer values to validate controls.
- **Agents cannot approve.** Only `POST /api/approvals/{id}/decision` applies a change, and it is the human path.
- **The answer key stays out of reach.** Evaluator truth files must live outside anything the tool gateway can read.
- Every agent action emits a `Decision` (see `app/models.py`) so it appears in the Reasoning log.

## Intake notes

Intake writes require `X-SchoolTrace-Reviewer: local-reviewer`, which the UI supplies. This distinguishes
an intentional local reviewer operation; it is not authentication. Keep the server on loopback and use
synthetic/public records. Unknown workspaces and cross-workspace source IDs return 404.

Original uploads are immutable SQLite BLOBs, so a failed transaction cannot leave a DB/file-storage
mismatch. Parsing is synchronous and bounded for the small local demo. Staging, validation and commit
are atomic, persisted operations; a crash rolls back the active operation and previously saved previews
can be resumed. There is no extra worker service or queue yet.

CSV roles: chart, opening, ledger, payroll, grants, budget, invoice. Text roles: service, policy, document.
Amounts are exact decimal strings (major units) or integer minor units selected per file. Dates are
YYYY-MM-DD; opening balances are dated at the start of the period before activity. Header mapping is
explicit; canonical optional columns are recognized by name. Stable source IDs are required for CSV
records. Unsupported or malformed inputs never become accepted financial records.

No corrections, full report recomputation, live agent execution or automatic evidence verification are
performed by importing. Evidence attachment records a scoped resumption event for the future runtime.
