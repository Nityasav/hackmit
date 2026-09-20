# Sherlock — implementation specification

Updated 2026-09-20 after integrating main commit `55e1daf` into `max`, adding receivables tools and preserving the coverage layout patch. This is the canonical implementation overview; root `SPEC.md` points here. Code and tests take precedence over historical plans.

## 1. Product and boundaries

Sherlock reviews a company's supplied financial records and supporting documents. The current domain is SaaS-company accrual accounting, not the former school-board five-agent prototype. Some UI labels still say institution and persisted identifiers retain SchoolTrace names. Do not restore removed school/grant/payroll-agent modules from historical documentation.

A user creates a workspace, uploads and validates records, commits them, starts an investigation, reviews evidence and makes decisions. There are no preloaded institutions, demo runs or seeded findings. Test fixtures must be deliberately imported and kept separate from real records.

The accounting profile is `SAAS_ACCRUAL_V1`. Synthetic workspaces support USD; public-document workspaces also support CAD, EUR and GBP but do not unlock USD accounting simply by supplying a document. No statutory audit opinion, full-population completeness or real-world financial posting is implied.

## 2. Frontend and workflow

| Destination | Route | Purpose |
| --- | --- | --- |
| Books | `/` | Workspace dashboard, CSV import, coverage, documents, record search/export |
| Investigation | `/investigation` | Objective, agent execution, conversation, progress, decisions and record checks |
| Briefing | `/briefing` | Findings, review follow-up and report export |
| Access / Login | `/access`, `/login` | Access management and web authentication |

Normal sequence: create → upload → preview/map → commit → investigate → review/export. Neither selecting files nor committing an import starts a paid run.

Preserve the monochrome design and magnifying-glass identity. Copy should describe an action or limitation briefly, not repeat marketing claims. Preserve quoted evidence and user content. Do not restore the removed standalone Running the agents/Open investigation or File updates panels on Books.

Books retains workspace creation and progress. Coverage requirements start collapsed, grouped into required, optional and supplied. Cards use equal-height grid rows, consistent gaps and bottom-aligned settings/actions; mobile becomes one column. Native file inputs are hidden behind explicit black chooser buttons. Institution inputs remain compact with label clearance and inset focus outlines. Do not fix overlap by making controls excessively tall.

`DataRequirements` handles a missing or malformed `requirements` array as an API compatibility warning, not an empty all-clear. `SourcesPanel` retains mapping, reviewer-supplied values, exclusions, saved imports, source history and evidence-request support. Removing a panel must not remove its backend capability.

## 3. Architecture

| Layer | Source | Responsibility |
| --- | --- | --- |
| Frontend | `web/src/app`, `components`, `lib` | Next.js 16, React 19, TypeScript, Tailwind; API contracts, state and navigation |
| HTTP API | `api/app/main.py` and routers | FastAPI endpoints, access and request limits |
| Intake | `ingestion.py`, `roles.py`, `requirements.py` | Validation, versions, snapshots, coverage and editable settings |
| Persistence | `db.py` | SQLite records, sources, imports, decisions and event history |
| Agent contract | `agents/registry.py`, `schemas.py` | Hierarchy, dependencies, scope, tools, reviewers, budgets and outputs |
| Execution | `graph/build.py`, `state.py`, `escalation.py` | LangGraph routing, worker graphs, interrupts and SQLite checkpoints |
| Model runtime | `agents/runtime.py`, `tools.py`, `budget.py` | Tool loop, scoped reads, deterministic calculations, provenance and limits |
| Accounting | `accounting/` | Matching, reconciliation, statements, close, accruals, planning, variance, controls, audit and reporting |
| Conversation / memory | `agents/chat.py`, `memory.py`, `approvals.py` | Investigation conversation, human decisions and reviewed precedents |
| Projection / review | `projection.py`, `reviews.py`, `updates.py` | Dashboard projection, deterministic scans, follow-up and snapshot differences |
| Documents | `document_processing.py`, `extraction.py`, `extractor_server.py` | Original storage, preprocessing, extraction review and model lifecycle |

The current runtime **uses LangGraph**; descriptions of a custom five-agent coordinator are obsolete. Maintain one authoritative registry and one dashboard projection rather than duplicating state.

## 4. Sources, validation and coverage

Workspace configuration includes name, kind, entity type (`company`, `subsidiary`, `group`), jurisdiction, currency, period and scope. Settings include home tax jurisdiction, fiscal year end, materiality, approval limit and optional close target day. Setting keys and validation are defined in `requirements.py` and `SettingsUpdate`.

There are 21 structured CSV roles:

- Ledger: chart, opening, ledger.
- Purchases: vendors, purchase_orders, goods_receipts, vendor_invoices, payments.
- Sales: customers, customer_invoices, remittances.
- Cash: bank_transactions, processor_payouts.
- People/spend: payroll, expenses.
- Planning: budgets, forecasts, headcount.
- Controls: approvals, period_locks, tax_registrations.

Document roles are policy, contract, invoice, service, budget and document. A budget document is not a structured `budgets` table. A file labeled document does not satisfy arbitrary structured requirements.

CSV intake permits 30 files per batch, 10 MB per file, 50 MB total and 50,000 rows per file. The frontend limit now matches the backend so a complete 21-role pack can be selected together. Exact current columns and units come from `roles.FIELDS` and `/api/roles`; monetary calculations use integer cents. Do not invent values to force validation.

Auto-detection matches complete schemas, not filenames alone. The frontend suggests mappings; backend detection validates committed/recovered records. Ambiguous files remain unresolved. Refresh sources can stage a recovery import for CSVs previously stored as documents; recovery still requires review and commit. It must preserve original source bytes/history and avoid repeat imports.

Import states include needs_mapping, needs_review, ready_to_commit and committed. Invalid rows block publication unless explicitly excluded with a reason. Source versions, stable keys, hashes and idempotency checks preserve provenance and prevent double counting. New records create a new snapshot; stale review results must not appear current.

There are 31 coverage requirements: 21 CSV roles, five named document roles and five settings. Some are optional. Coverage reflects supplied inputs, not successful analysis, a clean audit or verified completeness. A CSV-only pack with all settings satisfies 26/31; policy/contract/invoice/service/budget evidence remains document-specific.

Relevant APIs: workspace creation/settings; imports and commit; sources/detect; coverage and requirements; source download/spans; record date search and CSV export. Use current request models, not examples in old plans.

## 5. Agent hierarchy and execution

Twenty-two registry entries means **one orchestrator + four workers + 17 specialists**, not 22 specialists.

| Worker | Specialists |
| --- | --- |
| A — Treasurer | A1 Accounts Payable; A2 Accounts Receivable; A3 Bank Reconciliation; A4 Cash Management |
| B — Controller | B1 Month-End Close; B2 Accruals & Adjustments; B3 Financial Reporting; B4 Close Review |
| C — FP&A | C1 Budgeting; C2 Forecasting; C3 Variance Analysis; C4 Strategic Planning; C5 Board Reporting |
| D — Audit & Controls | D1 Audit; D2 Controls Testing; D3 Audit Evidence; D4 Reporting & Filing |

The orchestrator is Chief Financial Agent. `WIRED_WORKERS = ("A", "B", "C", "D")`; all four branches are connected. Requirements gate execution. A registry entry or wired branch alone is not evidence of live model accuracy.

Substantive tools now cover:

- A1: three-way matching, duplicate checks, policy checks.
- A2: receivables aging and exact-reference cash allocation.
- A3: bank reconciliation and processor-payout decomposition.
- A4: cash projection.
- B1: close checklist; delegation is graph-owned, not a generic model tool.
- B2: balanced proposed accrual journals for unbilled deliveries.
- B3/B4: statements and independent recomputation.
- C1–C5: budget rollup, forecast comparison, variance drivers, explicit scenarios and management reporting.
- D1–D4: sampling/tracing, control tests, persisted evidence packs and reporting.

Receivables match customer, currency and a unique invoice reference. Partial balances age by due date. Repeated receipt references, duplicate invoice references, multi-invoice allocations without an allocation breakdown, and unreferenced receipts are not guessed. Excess stays unapplied; receipts after the as-of date are excluded. These are proposed allocations, not postings. Engine exceptions feed escalation instead of relying on model narration.

Scopes derive from declared requirements. Source citations must point to records actually read. Tool calls and model use are metered; unsupported tools fail explicitly. Financial figures come from deterministic calculations; prose must not manufacture an amount or missing evidence.

LangGraph persists checkpoints with AsyncSqliteSaver. Multiple human interrupts require an addressed decision; a paused run is not complete. Resume currently creates a fresh run meter while historical spend remains persisted. Review declarations and escalation are not a blanket guarantee of sequential independent review of every claim; validate the actual graph path before making that claim.

Even specs marked `llm=False` can use the shared model runtime for narration/judgment. The flag describes deterministic work, not a promise of zero model calls. Model availability, valid server credentials, budgets and missing inputs can still block a run.

## 6. Reports, decisions and memory

Keep deterministic checks, model proposals, reviewer verdicts and human approvals distinct. Preserve source/line/page references and calculation provenance. Avoid summing overlapping exposures into invented savings.

Reports summarize supplied records. Statements, budget comparisons and cash flow tools are implemented, but they are management outputs, not a certified statutory filing. Journal proposals and human decisions do not post to an external ledger or release payments.

D3 collects actual decisions, links and precedent checks. Empty decision history must remain empty until work occurs; fixture uploads must not fabricate an audit trail.

Within-workspace approval precedent and cross-period memory are separate mechanisms. A new workspace may explicitly continue a prior period; reviewed precedent can then be checked for applicability. This is not automatic model training, unrestricted self-modification or approval bypass.

Active records and coverage are loaded for runtime use; do not claim an investigation is isolated from concurrent commits without validating its snapshot behavior.

## 7. Documents and extraction improvement

The current Books document chooser accepts PDF. Review extracted values against their original pages, correct them, and stage through intake before commit. A successful upload alone does not create validated ledger rows. Public documents and CSV records are different evidence paths.

Lower-level preprocessing and extraction modules retain additional format handling; supported UI inputs are narrower. Do not promise OCR availability from a library import alone: check installed dependencies and server configuration. XLSX and live ERP/bank connectors are not implemented by this workflow.

The extraction lifecycle includes model registration, predictions, corrections, consent, grouped datasets, export, paired evaluation, promotion, rollback and retirement. Most administration remains API-level. Fine-tuning and supplying a usable model artifact remain external work.

Promotion gates in `extraction.py` require held-out volume and groups, schema validity, precision/recall, citation/abstention accuracy, critical exactness, bounded unsupported values, and no baseline/per-role regression. These are policy thresholds, not achieved scores. Keep related templates/institutions grouped across splits; do not leak gold labels to inference.

## 8. Development and deployment

API: from `api/`, run `uv sync` and `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`. Web: from `web/`, run `bun install` then `bun dev` (port 3000). A server started without reload must be restarted to use backend changes. Do not run a production build over a running development build directory.

Keep credentials in ignored server environment files. Never put model keys in frontend code or fixtures. Important current settings:

- `OPENAI_API_KEY`; model tiers `AGENT_MODEL_SOL`, `AGENT_MODEL_TERRA`, `AGENT_MODEL_LUNA`.
- `AGENT_RUN_CAP_CENTS`, `AGENT_DAY_CAP_CENTS`; pricing configuration in `agents/budget.py`.
- `SCHOOLTRACE_DATA_DIR`, local users, public-host and allowed-origin settings.
- `NEXT_PUBLIC_API_URL`; Supabase web URL and publishable/anon key.
- Extraction endpoints/artifact configuration as consumed by the extraction modules.

Configured model identifiers and prices must match the deployed provider; defaults are not proof of availability. Old CFO/SPECIALIST model environment names are not substitutes for the registry's current tier configuration.

Supabase web login and backend authorization are distinct. Hosted access requires backend credentials, correct origins, persistent storage and appropriate isolation; a Vercel frontend alone does not supply these. Retain compatibility environment/database names where needed.

## 9. Verification and synthetic fixtures

The latest regression run and implementation checks are recorded below. These are offline checks, not a 22-agent live benchmark or model accuracy score.

`fixtures/generate_saas.py` creates deterministic fictional CSV books and separate event/defect truth. Seed 7, September 2026 produces 699 baseline records or 719 records with six planted control/matching defects and three benign lookalikes. Journals, opening balances, payroll and processor payout arithmetic are checked. Baseline does not mean no legitimate variance, unpaid invoice or evidence gap.

`fixtures/validate_saas_pack.py` imports all 21 CSV roles through a temporary FastAPI database with auto-detection, commits, checks coverage and invokes substantive tools for all 17 specialists. It makes no paid model calls and creates no fake decisions. Its saved outputs are regression observations, not independent ground truth. CSV packs cannot supply policy or contract documents or prove extraction quality.

Test human approvals/resume, conversation, evidence history, cross-period memory and actual provider responses separately. Expected answers must stay outside agent-readable upload folders.

## 10. Maintenance rules and remaining limitations

### September 20 demo workflow additions

- Investigation exposes **Ask the CFO agent** and a confirmed **Run financial audit** action. The latter runs deterministic checks, then routes a request through all four worker domains. The 17 specialists retain input, scope and budget gates; blocked work is disclosed rather than marked successful. This is an automated supplied-record review, not a certified audit.
- `agents/activity.py` records actual graph starts, tool calls, completions, failures and human-review stops. `/agents/activity?thread_id=...` feeds a polling domain grid and timestamped timeline. It does not expose chain-of-thought or invent agent interactions. Older runs have no activity events.
- `agents/continuation.py` unifies the common approval path with durable graph resume and updates conversation state. Standalone conclusions are already finished: approving resolves their task, while **Revise instructions and rerun** explicitly starts new paid work. Original decisions remain in history. Approval does not create evidence, post entries or pay invoices.
- Books allows withdrawing an active committed source through a confirmed, revision-checked DELETE request. `source_removal.py` deactivates its records and creates a new snapshot; original bytes and prior snapshots remain. This is removal from active books, not irreversible erasure. Reimporting identical versions does not restore withdrawn records automatically.
- Briefing exports an authenticated, paginated ReportLab PDF with findings, evidence locators, status counts, follow-up, history and limitations. Markdown remains an API compatibility format. New agent decisions record snapshot provenance; older decisions use the most recent preceding snapshot as a historical approximation.
- A2 and C3 expose deterministic receivables-aging and budget-variance graphics with source references, separate from model conclusions. The transaction list is collapsed and searchable; review history has aligned filters and expandable detail rows.
- Offline verification includes source-removal scope/revision checks, PDF generation, graph continuation, and full-review routing. No paid provider run or live-model quality benchmark was performed for these additions.
- Final checks: **397 backend tests passed**, with one dependency deprecation warning; frontend lint and TypeScript passed. The full-review regression exposed concurrent worker subgraphs returning shared scalar fields. `WorkerOutput` now limits their return schema to accumulated results, avoiding conflicting writes when all four domains execute together.
- Task outputs: the runtime persists `agent.deliverable` events containing the original objective, snapshot, result and calculations used. All 17 specialists expose a task-specific text/PDF deliverable through `/agents/deliverables/{decision_id}` (and `/pdf`), opened from Agent tasks. No read/export starts another model or recalculates against newer books. Older tasks explicitly disclose missing original prompts/calculations. The roster's unrelated standalone chart buttons are removed; saved aging/variance charts appear only when that task ran the relevant calculation.
- Audit approval cards support both legacy string agent identifiers and structured `{id, name}` identifiers; React render tests cover the previously crashing saved-run shape. Latest backend suite: **416 passed**; both UI rendering regression tests pass.

Before changes inspect Git status/branch, preserve pending work and read applicable AGENTS.md. Keep this spec and root pointer consistent. Historical plans, tracker entries and READMEs can describe earlier phases; do not restore obsolete architecture from them.

### Current CFO conversation and deliverable behavior

- CFO chat uses a domain-restricted structured Responses call to answer accounting questions from workspace-local recent turns, saved task results and calculated evidence, or dispatch precisely named specialist IDs. Explicit FP&A requests cover C1–C5. Full financial reviews bypass conversational routing and request all four domains. Conversational explanations are advisory, not new verified findings.
- Context is bounded and historical snapshots are labeled. No provider-side conversation is stored (`store=False`). Chat usage is persisted and included in daily spending; the conversation and dispatched graph share a run meter. Unknown specialist IDs or invented saved-result references fail closed.
- New graph runs order dependent deliverables after their contributors. Scoped, attributed handoffs and historical pointers are shared within bounded context, without granting source access or bypassing citation checks. Legacy paused runs retain their original topology. Invalid citations get one bounded correction opportunity; unsupported evidence remains refused.
- Every saved CFO response can export a request-specific PDF. Every specialist exposes its saved task deliverable in the roster immediately after running and in Agent tasks; errors stay beside its input. Previous decisions are collapsed into compact summaries with details on demand.
- Full-review deliverables include only the recorded run's conclusions and exact saved scan, plus domain coverage, unresolved work and next steps. Legacy runs disclose unavailable scan provenance rather than borrowing a later scan. Findings are not an audit opinion or a completeness guarantee.
- Verification: **430 backend tests**, **4 frontend rendering tests**, TypeScript and lint pass. Mocked-provider tests cover explicit FP&A dispatch, conversational follow-ups without reruns, export isolation and citation recovery. No paid live-provider benchmark was run; provider behavior and financial accuracy still require real-world validation.

Known limits: no live-model benchmark established by the current offline run; provider/deployment configuration needs environment-specific verification; CSV-only evidence does not satisfy document requirements; no external posting, payment execution or statutory audit certification; extraction model quality requires its own held-out benchmark. Wiring and passing arithmetic tests are necessary, not sufficient, for production financial assurance.
