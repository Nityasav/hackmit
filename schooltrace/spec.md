# Sherlock — current product and implementation specification

Updated: 2026-09-20. This is the canonical specification for the current working tree, including the uncommitted cleanup on `max`. Read this before changing the product. Repository-root `SPEC.md` points here; `PROJECT_TRACKER.md` records status and the next handoff. Code is the evidence for implementation claims. Historical plans are design context, not proof that a feature exists.

## 1. Product and user intent

Sherlock helps education finance teams review supplied financial records with five cooperating agents. A director creates an institution, uploads records, commits a validated snapshot, asks an investigation question, examines cited findings, records decisions, and exports a briefing. Institutions are user-created; no specific school is the target.

The interface must remain compact, professional, and understandable without a demonstration. Preserve the existing monochrome palette, typography, magnifying-glass identity, and three main destinations. Do not reintroduce preset institutions, starter packs, recorded findings, scripted investigations, or automatic paid runs. Test data stays in isolated test environments.

Capitalization uses sentence case for labels and statuses: School, District, Board, University, Needs evidence. Preserve acronyms such as CFO, AP, PDF, CSV and ID. Display labels must not change API enum values, CSV headers, filenames, institution names, or source quotations. Nested full-width form controls have a separate row and label clearance through `web/src/app/globals.css`.

Product copy should name the task and next action directly. Prefer short headings such as Review scope, Agent team, Findings and Source evidence. Avoid hackathon slogans, repeated claims about AI, conversational filler and long explanations of implementation details. Keep source quotations and user-authored content unchanged. Preserve necessary information about review scope, paid calls, data transmission and irreversible actions. Shorter copy should fit existing containers without fixed heights or forced line lengths.

## 2. Current navigation and workflow

| Screen | Route | Implementation | User action |
| --- | --- | --- | --- |
| Books | `/` | `SourcesPanel`, `DocumentIntake`, `FileUpdates`, `GuidedWorkflow` | Create institution; upload, map, validate and commit records; add later revisions |
| Investigation | `/investigation` | `components/investigation/` | Set objective; start five-agent review; inspect progress, sources, findings and precedent |
| Briefing | `/briefing` | `ReviewWorkspace` with `section="reports"` | Review snapshot findings, limitations and saved follow-up; export Markdown or print |
| Access | `/access` | Access page and local API access routes | Inspect local access, sign in when configured, delete a workspace |
| Login | `/login` | Supabase auth and `src/proxy.ts` | Authenticate to the web application |

`web/src/lib/tabs.ts` owns primary navigation. Historical `/command`, `/board`, `/findings`, `/reports`, `/learning`, and `/cfo` page references are not current destinations. Some legacy tab identifiers remain in bundle contracts; do not confuse them with public routes. Current `disabled_tabs` is empty to avoid returning removed navigation identifiers to the frontend schema.

The normal sequence is create → upload → preview/map → commit → investigate → review/export. Committing data does not call a model. Starting a live investigation does. Books still exposes separate CFO, Grants and Auditor controls as well as the main Investigation flow; this is existing duplication, not an additional orchestration system to build.

## 3. Architecture and ownership

| Layer | Files | Responsibility |
| --- | --- | --- |
| Web | `web/src/app/`, `web/src/components/` | Next.js 16 App Router, React 19, TypeScript, Tailwind 4 |
| Client state | `web/src/lib/store.ts`, `data.tsx`, `schemas.ts`, `types.ts` | Zustand selection, workspace loading, polling, Zod validation and typed responses |
| HTTP clients | `web/src/lib/api.ts` | Axios, API URL selection, reviewer header, cookies, 20-second request timeout, error mapping |
| API routing | `api/app/main.py` | FastAPI routes and shared middleware |
| Persistence | `api/app/db.py` | SQLite schema and transactional storage of originals, records, snapshots and run history |
| Intake | `api/app/ingestion.py` | CSV/text validation, provenance, source revisions, atomic snapshot commits and coverage |
| Accounting | `api/app/accounting/` | Exact integer-cent payroll, AP, grants and review checks |
| Coordinator | `api/app/cfo/` | Bounded planning, dispatch, review cycles, execution events and report persistence |
| Agent adapters | `api/app/agents/`, `api/app/integrations/` | Scoped source tools, specialist/reviewer roles and model adapters |
| Dashboard projection | `api/app/projection.py` | Sole dashboard Bundle builder from persisted evidence and runs |
| Decisions | `api/app/approvals.py`, `reviews.py` | Approval proposals, reviewed precedent, deterministic scans and human follow-up |
| Extraction | `document_processing.py`, `extraction.py`, `extractor_server.py` | PDF/image/text preprocessing, local inference interface, corrections, evaluation and model releases |
| Updates | `api/app/updates.py` | Snapshot differences and explicitly requested rescans |
| Web identity | `web/src/lib/supabase/`, `web/src/proxy.ts` | Supabase session validation; separate from API authorization |

The runtime uses a custom Python coordinator, not LangGraph. LangGraph was previously proposed; it is not an installed orchestration dependency. Keep the existing structure compact and avoid creating parallel stores or alternative bundle builders.

## 4. Documents, financial records and updates

Workspace IDs are `ws-` plus 16 hexadecimal characters. Workspace creation records name, entity type, jurisdiction, currency, period and scope. Current data-origin values are `synthetic` and `public`; authorized confidential institutional mode is not implemented by merely changing these labels.

The accounting profile is `US_DISTRICT_MANAGEMENT_ACCRUAL_V1`, with USD integer cents. Other supported currencies are available for public-document exploration. This is a management accounting profile, not a statutory Canadian school-board or complete GASB adapter.

Structured intake accepts CSV and UTF-8 TXT/Markdown: up to 20 files, 10 MB each and 50 MB per batch. File roles include chart, opening, ledger, payroll, grants, budget, invoice, fees, collections, deposits, sponsorships, policy, service and document. Required columns and validation live in `ingestion.py`; clients must not invent financial defaults to force an import through.

An import progresses through `needs_mapping`, `needs_review`, `ready_to_commit`, and `committed`. Confirm mappings, exact amounts, dates and controls before commit. Invalid rows block publication unless explicitly excluded with a reason. Original bytes and source hashes remain available for evidence inspection. A balanced journal is an arithmetic control, not proof of completeness.

Source identity combines workspace, role, source system, stable record ID and version. New versions supersede active records while preserving history. Duplicate-only imports must not double count. Commit uses expected preview versions and idempotency keys; stale writes return conflicts. Snapshots pin records and provenance for an investigation.

PDF, PNG, JPEG, TXT and Markdown documents use the extraction path. Originals are preserved; preprocessing produces page text/images. Review extracted fields and citations before staging them through normal financial intake. Extraction approval alone does not commit ledger records. XLSX and live ERP/bank connectors are not implemented.

Continuous uploads are supported. `GET /api/workspaces/{ws}/updates` compares the latest two snapshots. `POST .../updates/scan` runs deterministic checks and optionally starts a five-agent investigation with `live: true`. This requires explicit user action. It does not run silently on every upload and is not a dependency-aware selective recomputation engine. Results from older snapshots must remain visibly stale.

## 5. Agents and orchestration

| Role | Runtime ID | Job |
| --- | --- | --- |
| CFO Agent | `cfo` | Plans tasks, manages bounded follow-up and synthesizes the final briefing |
| AP & Payments | `ap` | Reviews invoices, purchase/receipt references, duplicate candidates and payment support |
| Payroll & Budget | `py` | Reviews payroll reconciliation, allocations and budget evidence |
| Grants & Compliance | `gr` | Reviews award terms, eligibility periods and supplied charges |
| Internal Auditor | `au` | Retrieves original evidence independently and reperforms calculations before accepting claims |

The document extraction model is a separate input-processing component, not a sixth investigator. The partner's future fine-tuned local model plugs into this extraction interface.

The main UI posts `workflow: "five_agent"` to `/api/cfo/runs`. `cfo_factory.py` wires `IntakeDataSource`, three `SnapshotSpecialist` adapters and `SnapshotAuditor`. The coordinator validates the plan and evidence scope, schedules independent tasks within concurrency limits, requests independent review, permits bounded revisions and persists the report. Provider failures and budget exhaustion remain visible; there is no fixture fallback.

Standalone routes `/api/workspaces/{ws}/agent-runs` support `cfo`, `grants_compliance`, and `internal_auditor`. These have a separate synchronous execution loop and persist to `agent_runs`; coordinator runs persist to `cfo_runs`. Both share the intake database and dashboard projection. Do not describe them as one unified execution loop. Standalone Auditor requires existing preparer findings and can leave targets unreviewed.

Models interpret sources; accounting code supplies monetary results. A supported amount requires a published calculation and provenance. Auditor acceptance is a bounded claim review; human approval remains separate. Agents cannot post journals, release real payments or change payroll through their evidence tools. Uploaded instructions are untrusted document content.

## 6. Findings, decisions, reports and memory

`projection.py` derives dashboard tasks, findings, decisions, approvals, reports and precedent from saved runs. It must never populate an empty workspace with unrelated results. `reviews.py` also exposes a snapshot review feed that combines deterministic checks, standalone candidates, coordinator claims and follow-up history; the Briefing screen currently consumes this feed.

Keep candidate findings distinct from Auditor-accepted claims and human decisions. Preserve source identifiers, line/page locators, calculation references and snapshot IDs. Missing evidence remains an unresolved question. Do not sum overlapping exposure, reclassification and cash-impact amounts into a savings total.

`approvals.py` saves human decisions and can derive approved-scenario effects from supported balanced proposals. `reviews.py` follow-up actions track owner, note and status. These are different records and APIs. Neither changes an external financial system. Reports can be exported as Markdown and printed; a complete statutory statement package is not implemented.

Reviewed precedent exists today: human approval/rejection creates scoped precedent; later runs can record applicability checks. The UI projects precedent as playbooks and shows applied/declined checks. This does not mean agents train themselves, rewrite prompts, or implement the earlier proposed automatic playbook discovery and replay system.

## 7. Extraction model improvement

The API supports original-document storage, model registration, predictions, human corrections, training consent, grouped frozen datasets, training export, paired evaluations, promotion, rollback and retirement. Most lifecycle operations are API-level features; Books primarily exposes upload, extraction, correction and staging.

Each extracted observation carries a status (`present`, `missing`, `ambiguous`, `unreadable`), value and page/character citation. Invalid or unsupported values cannot become accepted financial records. Dataset grouping prevents related institution/template documents from crossing train/evaluation boundaries. Model manifests record training hashes/groups, supported roles and artifact identity. Gold labels must not be sent to inference.

Current promotion policy in `extraction.py`: at least 20 held-out documents, 3 groups and 100 present fields; schema validity 100%, precision 99%, recall 95%, citation accuracy 98%, abstention accuracy 95%, critical exactness 99%, unsupported rate at most 1%. Candidate metrics cannot regress against baseline; each supported role needs at least three documents and no per-role regression. Promotion requires an admin, current evaluation policy, unchanged model identity and active-version consistency.

These are configured gates, not achieved model scores. Training and supplying a fine-tuned artifact remain external work. The repository includes a local model serving adapter; availability and quality require an actual configured artifact and benchmark evidence.

## 8. Running and deployment boundaries

Start the web app in `web/` with `bun install` then `bun dev`; start the API in `api/` with `uv sync` then `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`. The browser uses port 3000. Keep server API keys in ignored `api/.env`; never copy them into client code or docs.

| Configuration | Purpose |
| --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Web login configuration in `web/.env.local` |
| `NEXT_PUBLIC_API_URL` | Browser records API; defaults to localhost:8000 |
| `NEXT_PUBLIC_CFO_API_URL` | Optional coordinator URL override |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Server model credentials and default selection |
| `CFO_MODEL`, `SPECIALIST_MODEL`, `GRANTS_MODEL`, `AUDITOR_MODEL` | Role/runtime model overrides; verify the consuming adapter |
| `CFO_PROVIDER`, `SPECIALIST_PROVIDER` | Model-provider selection for coordinator adapters |
| `SCHOOLTRACE_DATA_DIR` | Intake database directory |
| `SCHOOLTRACE_USERS` | Optional local API password accounts, roles and workspace access |
| `SCHOOLTRACE_EXTRACTORS` | Registered local extraction endpoint/artifact configuration |

Supabase authenticates the web app, but the FastAPI access layer separately uses loopback restrictions and optional local accounts. A web login does not establish API tenant isolation. Deploying the frontend to Vercel alone does not host this Python API or make a visitor's localhost available. A hosted backend, matched authorization, allowed origins and persistent storage remain required for a usable public deployment.

Compatibility names such as `SCHOOLTRACE_*`, the reviewer header, SQLite filename and schema identifiers remain where needed. Product branding is Sherlock. Do not rename persisted contracts casually.

## 9. Validation and known gaps

The last completed backend run before this documentation/capitalization update reported 339 passing tests and 9 skipped tests. These are offline unit/integration checks, not model accuracy scores. Opt-in provider evaluations can cost money and require separate reporting of model, dataset, denominators and failures. Lint/build validate frontend integration; browser verification is needed for layout and interaction changes.

Known gaps: hosted API/auth integration; trained extractor artifact and independently measured quality; XLSX/connectors; complete statutory financial statements; full structured three-way matching; automatic playbook generation/replay; full dependency-aware rescans; external financial posting. Current client requests have a 20-second timeout while standalone reviews can run longer, so long synchronous reviews warrant integration testing. Do not mark a gap complete from a screenshot or a successful HTTP response alone.

## 10. Context maintenance rules

Before work, inspect Git branch/status and preserve pending edits. Read `web/AGENTS.md` for frontend changes. Read only the modules relevant to the feature after this overview. Update this spec when routes, contracts, model roles, authorization boundaries or implemented capabilities change. Record verified outcomes and remaining work in `PROJECT_TRACKER.md`.

Use `contracts/README.md` and current models for endpoint details. `INGESTION_PLAN.md` and `REWIRING_PLAN.md` retain historical design context and may contain outdated names or proposed work. Earlier references to deleted documents or prototypes are not dependencies and must not be used to reconstruct preset content.
