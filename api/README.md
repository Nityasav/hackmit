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
| `app/agents/cfo.py` | Agent design | First live CFO agent, scoped snapshot tools, OpenAI adapter and run persistence |
| `app/cfo/` | CFO coordination | Separate bounded coordinator, scripted harness, persisted runs and specialist/reviewer ports |
| `app/integrations/` | Integration | Read-only intake bridge and adapter factory; live specialist and auditor registration pending |
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

No corrections, full report recomputation or automatic evidence verification are performed by importing.
Evidence attachment records a scoped resumption event for the future multi-agent runtime.

## CFO triage agent

This is the live Command center path. The separately merged `/api/cfo/runs` coordinator and `/cfo`
page are documented in `app/cfo/README.md`; live orchestration still requires specialist/auditor adapters.
Both route families coexist. The coordinator's optional local provider is an experimental CFO adapter,
not the planned fine-tuned document extraction component. `OPENAI_MODEL` selects triage, while `CFO_MODEL`
selects the coordinator preview model. The two run stores and execution loops are not yet unified.

Set `OPENAI_API_KEY` in ignored `api/.env`, which loads automatically without overriding existing
environment variables. `OPENAI_MODEL` defaults to `gpt-5.4-mini`. Never place the key in `web/.env.local`
or send it from the browser. `POST /api/workspaces/{ws}/agent-runs` accepts
`{snapshot_id, request_id, focus}` and runs one bounded CFO triage against the current snapshot;
`GET` lists saved runs. The provider request uses `store=False`.

The agent can read only scoped workspace context, committed source lines, paginated snapshot records and one
deterministic ledger control calculation across ALL pinned ledger records. Twelve actual tool calls,
2,500 output tokens per response, a conservative 100,000 total-token budget, a 60,000-byte conversation
cap, and a four-minute run deadline bound execution. Requests have a maximum 60-second timeout and
no automatic paid retries. Provider storage is disabled; this is not a claim about all provider retention.
Request IDs prevent duplicate execution. A changed snapshot returns 409; running rows older than the
deadline plus 30 seconds become failed, permitting retries after a process interruption. Each completed
tool step persists arguments, input hash, output, output hash, agent, snapshot and latency; provider failures
retain that history and show sanitized errors. Interrupted runs restart explicitly rather than resuming automatically.
The server checks every submitted
citation against the original line before saving candidate findings. This is live triage, not independent
auditor review, report generation, an audit opinion or authority to apply an adjustment.
