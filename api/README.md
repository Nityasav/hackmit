# Sherlock API

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000   # http://localhost:8000/docs
uv run pytest                                       # accounting invariants
```

## Agent evaluation

`uv run pytest -q` runs offline unit/integration/safety tests without provider charges. The cross-agent
matrix covers forbidden tools, malformed/incomplete provider responses, failure-history retention,
snapshot changes during a run, exact money guards and seeded allocation invariants.

Fresh model development evaluations are deliberately opt-in and billable:

```bash
SCHOOLTRACE_LIVE_EVAL=1 SCHOOLTRACE_EVAL_OUTPUT=/absolute/path/outside/runtime uv run pytest -q -s tests/test_agent_live.py
```

They use isolated temporary databases and fictional documents, never existing user workspaces. The
local server key loads from ignored `.env`. Four cases exercise CFO, Grants and Auditor: allocation
conflict, supported full allocation, missing service support and document instruction injection. A fifth
case supplies a deliberately false scripted preparer claim to test a **live** Auditor rejection. Saved
artifacts contain source/prompt hashes, outputs, usage and timings, but never keys. Recheck saved sources
and arithmetic without model calls with `SCHOOLTRACE_EVAL_OUTPUT=/absolute/path uv run pytest -q
tests/test_agent_live.py -k saved`.

These are developer-authored cases, **not** the independently held-out benchmark from
`schooltrace/DATA_AND_EVALUATION.md`. HTTP completion and exact citations do not establish semantic
correctness. Review saved prose against the predetermined expected dispositions; preserve failed runs.
Full confirmed-issue precision/recall, AP/payment controls, memory ablation, playbook replay and report
consistency remain separate gates, not implied passes from this suite.

## Layout

| Path | Owner | What goes here |
| --- | --- | --- |
| `app/main.py` | Functionality | HTTP endpoints (see `contracts/README.md`) |
| `app/models.py` | Functionality | Pydantic mirror of the bundle contract |
| `app/db.py` | Functionality | SQLite schema, transactions, original bytes and local events |
| `app/ingestion.py` | Functionality | CSV/text parsing, mappings, validation, immutable commits, coverage and evidence requests |
| `app/accounting/` | Functionality | Exact integer-cent math and ledger invariants L01–L13 |
| `app/agents/cfo.py` | Agent design | First live CFO agent, scoped snapshot tools, OpenAI adapter and run persistence |
| `app/agents/grants.py` | Agent design | Grants & Compliance instructions, award-window checks and exact supplied-payroll totals; shares the triage runtime |
| `app/agents/auditor.py` | Agent design | Independent direct-run review with pinned targets, original-source reperformance and provenance gates |
| `app/cfo/` | CFO coordination | Separate bounded coordinator, persisted runs and specialist/reviewer ports |
| `app/integrations/` | Integration | Read-only intake bridge and adapter factory; live specialist and auditor registration pending |
| `app/workflows/` | Workflows | Workflow definitions and evidence-resumption states |

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
mismatch. Parsing is synchronous and bounded for local operation. Staging, validation and commit
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
`{snapshot_id, request_id, focus, agent?}` and runs one bounded review against the current snapshot;
`agent` defaults to `cfo`, or select `grants_compliance` or `internal_auditor`. `GET` lists the latest 20 runs per agent.
The provider request uses `store=False`. `GRANTS_MODEL` optionally overrides `OPENAI_MODEL` for Grants.

Grants adds `check_grant(award_id)`: exact totals of all pinned payroll allocations for that award,
inclusive service-period comparisons, ceiling comparison, source locators and input-ID hash. Missing
or ambiguous award definitions yield unknown comparisons, not clearance. Payroll and ledger are not
summed. These are supplied-payroll checks, not lifetime spend, remaining funding, eligibility decisions
or compliance certification. At least one known award must be checked when normalized award/payroll
records exist; unreviewed awards must be stated in limitations. Terms come only from uploaded evidence.
The direct-run Grants agent is not yet registered as an auto-dispatched coordinator specialist.

Internal Auditor requires current-snapshot preparer findings (otherwise 409). It pins the latest CFO
and Grants results at start and retrieves up to four candidates per tool page. Its structured `reviews`
identify exact finding IDs with `accept`, `reject` or `needs_evidence`, rationale, citations and next action.
Accept/reject requires fresh reads of original cited lines; acceptance also requires supporting ledger/
grant calculations to be rerun. Auditor calculations reparse original CSV bytes with the shared exact
parser and compare against pinned records; this is independent execution, not a second parsing algorithm.
Integrity mismatches block acceptance. `AUDITOR_MODEL` overrides `OPENAI_MODEL`; model diversity is optional.
Results include `review_scope` counts and unreviewed IDs. Same-snapshot preparer reruns invalidate review
targets (`review_targets_current: false`); verdicts never transfer to new findings or mutate originals.
This direct reviewer is not yet registered with the separate coordinator's Auditor port.

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
