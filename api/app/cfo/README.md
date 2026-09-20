# CFO integration contract

This package owns planning, bounded delegation, independent review gates, follow-up
decisions, briefings, reports, and CFO run checkpoints. It does not own specialist
reasoning, source ingestion, financial postings, or human approval.

The implementation uses explicit Python orchestration with typed ports. No agent
framework dependency is required. Research and presentation wording live in
[`docs/research/cfo-coordination.md`](../../../docs/research/cfo-coordination.md).

## Try it without a key

From `api/`:

```powershell
uv sync --extra cfo
uv run python -m app.cfo --award-share 60
uv run python -m app.cfo --award-share 80
uv run python -m app.cfo --missing-service
uv run uvicorn app.main:app --port 8000
```

These are explicitly **scripted** collaborator examples. They exercise the real
coordinator and integer-cent calculation engine; they are not real AI investigations.

Set `NEXT_PUBLIC_CFO_API_URL=http://127.0.0.1:8000` in `web/.env.local` and open
`http://localhost:3000/cfo`. The existing eight dashboard tabs remain independent:
this feature does not overwrite their fixtures or require a bundle-schema change.

## API

- `POST /api/cfo/runs`: `{ "workspace": "sandbox", "objective": "Review payroll allocation", "mode": "scripted" }` → 202 with run ID.
  `workspace` is `sandbox`, `mit`, or an intake workspace ID (`ws-...`). Intake IDs
  require `mode: "live"`; the scripted harness answers for `sandbox` only.
- `GET /api/cfo/runs/{id}`: plan, task states, accepted claims, unresolved items, activity records, briefing, report.
- `GET /api/cfo/runs/{id}/report`: Markdown report, or 409 until published.
- `GET /api/cfo/workspaces/{workspace}/latest`: latest saved run.

Poll the run endpoint while its status is queued/planning/running. A second concurrent
run for the same workspace returns 409. Missing configuration returns 503; it never
silently switches a requested live run to fixtures.

Modes:

| Mode | CFO | Data / specialists / auditor |
| --- | --- | --- |
| `scripted` | Fixed integration harness | Scripted examples |
| `model_preview` | Real configured model | Scripted examples |
| `live` | Real configured model | Registered integration adapters |

`model_preview` lets you test the actual CFO planner and writer before Linda and Maxim
finish. It is not an evaluation of specialist reasoning or a live financial review.

## Model configuration

For the initial demo, use OpenAI for the CFO and evaluate local Qwen separately.
No model ID is silently assumed: choose one available to your account that supports
Responses structured output. Do not use the model string from the UI fixtures.

```powershell
$env:CFO_PROVIDER = 'openai'
$env:CFO_MODEL = '<available-model-id>'
# Set OPENAI_API_KEY privately in the server environment; never in NEXT_PUBLIC_*.
uv run uvicorn app.main:app --port 8000
```

Or run an installed Qwen model through a local OpenAI-compatible server supporting
JSON-schema output (for example Ollama):

```powershell
$env:CFO_PROVIDER = 'local'
$env:CFO_MODEL = '<installed-qwen-model-name>'
$env:CFO_LOCAL_BASE_URL = 'http://127.0.0.1:11434/v1'
```

The local adapter uses a dummy credential and accepts loopback hosts only. It never
forwards OPENAI_API_KEY. Model calls use a 4,096-output-token cap, no SDK retries,
and the run's call timeout. Provider refusal, truncation, and invalid output fail
closed. Invalid synthesis falls back to accepted claims and exposes the limitation.

The API reads environment variables, not `.env` files automatically. To load an API
`.env` file, use `uv run uvicorn app.main:app --env-file .env --port 8000`.

## Linda: plug in the specialists

Implement the protocols in `ports.py`:

```python
async def investigate(task, scope, tools, dependencies, feedback) -> WorkerResult:
    ...

async def review(claim, scope, tools) -> Review:
    ...
```

Register specialist instances by role (`ap`, `py`, `gr`), and a separate auditor
instance. The CFO passes a scoped source/calculation inventory and completed dependency
results, not the entire conversation. `feedback` contains specific auditor challenges
and CFO instructions on the bounded retry.

Use `await tools.read_source(source_id)` and `await tools.calculate(calculation_id)`.
IDs come from `scope.sources` and `scope.calculations`, not hardcoded CFO assumptions.
Return typed claims with source IDs, an optional calculation ID, and an economic-event
key. The key should identify the same issue consistently across agents, e.g. record +
issue family + period. Return targeted `evidence_requests` when blocked.

Before accepting, the auditor must independently retrieve every cited source and
reperform the calculation through its own tools instance. The engine checks that
these calls actually happened. Agreement alone cannot pass the gate. Source retrieval
does not prove semantic correctness; the auditor remains responsible for evaluating
the content and challenging unsupported statements.

Every confirmed numeric amount belongs in a Calculation, not free-form prose. Specialist
internal LLM calls/token budgets remain Linda's responsibility; CFO accounting covers
its own model calls plus observed shared evidence-tool calls.

## Records: wired to intake; calculations still open

`app/integrations/cfo_intake.py` implements `DataSource` over the committed
intake snapshot, so a CFO run can read real uploaded records:

| Port method | Status | Backed by |
| --- | --- | --- |
| `snapshot(workspace)` | Implemented | `ingestion.coverage`: institution, period, profile, active committed sources, capability gaps and open evidence requests |
| `read_source(scope, source_id)` | Implemented | `ingestion.source_view`, bounded to 400 lines / 20,000 characters, refused unless the snapshot still matches |
| `calculate(scope, calculation_id)` | Payroll only | `accounting/payroll.py`: gross-to-net, total expense, allocation totals, ceiling excess, award-window and service-support tests, ledger tie. Other domains still fail closed |

The bridge reads only. It never stages, commits, mutates records or publishes
snapshots. Intake roles map to specialist domains as `invoice → ap`,
`payroll → py`, `grants → gr`, and everything else to `shared`.

Payroll amounts are published. AP and grant specialists can still only cite
evidence and explain a finding, and the scope carries that limitation as an
explicit gap. To close it for another domain, add deterministic calculations
bound to the snapshot in `app/accounting/` and publish them the same way:

```python
async def calculate(scope, calculation_id) -> Calculation:
    ...  # integer-cent amount, cash delta, impact category and source IDs
```

Calculation IDs are chosen by the data layer; publish their descriptions and
dependencies in the inventory returned by `snapshot`.

Keep arbitrary SQL, files, and evaluator truth outside these methods. The adapter
enforces institution/workspace access and immutable snapshots. Calculation IDs are
chosen by your data layer; publish their descriptions and dependencies in the inventory.
Every calculation has source IDs, integer-cent amount/cash delta, and an impact category.

The coordinator checks IDs, scope, source dependencies, and snapshot consistency; it
does not certify your calculation engine. A changed snapshot prevents publication of
accepted conclusions. New evidence should produce a new snapshot and a new CFO run;
automatic resume across changed snapshots is intentionally not implemented.

## Connect the adapters

`app/integrations/cfo_factory.py` already registers the intake data adapter and
the Payroll & Budget agent (`py`, see `app/agents/README.md`), which it omits
when no specialist model is configured. Add the remaining agents to the same
call when they exist:

```python
return Adapters(
    data=IntakeDataSource(),
    specialists={"ap": your_ap, "py": your_payroll, "gr": your_grants},
    auditor=your_independent_auditor,
)
```

Set `CFO_ADAPTER_FACTORY=app.integrations.cfo_factory:create_adapters` in the server
environment. With records registered but no agents, a live run stops with a 503 that
names the missing agents; it never falls back to the scripted harness. This is trusted server configuration, not user input. The factory is
synchronous and runs once per server process. Alternatively, set
`app.state.cfo_runtime = CFORuntime(repository, adapters)` in your application startup.

No changes to CFO internals or existing shared bundle types are needed. Map the CFO
run result to dashboard bundles in the eventual shared integration layer.

## Runtime boundaries

- At most eight planned tasks, two concurrent specialist calls, two review attempts,
  twelve evidence calls per actor per task, and one hundred evidence calls per run by
  default. Limits are validated; the planner cannot raise them.
- Twelve CFO model calls by default. The writer receives only accepted results and
  unresolved items. Context size is bounded; raw source text stays with specialists.
- The overall model cost of Linda's agents is not enforced here. Their adapters must
  enforce their own model limits and cooperate with cancellation.
- The same economic-event claim is deduplicated. Conflicting conclusions are withheld
  and retained as unresolved; original submissions remain in the activity record.
- No approval, payment, posting, external messaging, or playbook activation tool exists.
- Run checkpoints use a separate SQLite database (`CFO_DB_PATH`; default in API `.venv/`).
  Use a persistent volume/path when hosting. Run **one API worker**; this is not a
  distributed job queue. Interrupted runs are marked on next runtime initialization.
- This local hackathon API has no authentication or tenant isolation. Add your shared
  auth/access layer before exposing real institutional records or paid model execution.

## Verification

`uv run --extra cfo pytest` tests the real scheduler with controlled adapters, not LLM
quality. Coverage includes data-driven amounts, missing evidence, independent review,
retries, budgets, timeouts, DAG validation, concurrent work, source boundaries,
disagreement, persistence, stale snapshots, and invalid narrative fallback.

For sandbox-restricted Windows environments, supply a fresh writable test directory:
`uv run --extra cfo pytest --basetemp .venv/pytest-cfo-local`.

Live OpenAI/Qwen calls require credentials or a running local model and a separate
quality evaluation. They are not implied by passing these integration tests.
