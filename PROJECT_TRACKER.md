# SchoolTrace — project map, implementation tracker and handoff

Status: INTAKE + OPENAI CFO, GRANTS AND INTERNAL AUDITOR IMPLEMENTED — automatic orchestration and local-model training remain future work.
Updated: 2026-09-19.
Canonical location: `PROJECT_TRACKER.md` at repository root.
Repository: `/Users/max/Desktop/Projects/hackmit`.
Implementation branch: `max` tracking `origin/max`; started from `bc066ca`.

## 1. Read this first

Product: an AI-agent auditor and audit-preparation system for educational institutions. It collects records, checks accounting deterministically, coordinates specialist investigations and independent review, asks for evidence, and produces traceable reports with human-reviewed corrections.

It should work for any school, district, board or university; no specific real institution is the target. Real institutions need their own scope and accounting profile. The initial transaction demo uses fictional records.

User direction for this iteration:
- Write an implementation plan for getting documents and financial records into the product.
- Create a project-wide Markdown skeleton to track code creation and retain context.
- Reference the existing spec and the supplied Maximor challenge brief.
- Present plans for review before coding.
- A named school in the conversation was an analogy only; do not introduce a school-specific integration.

Max subsequently approved implementation and pushing to the current branch, requesting compact code with few folders. Intake has been implemented; use the latest checkpoint before choosing further work. Do not infer approval for the entire future agent roadmap.

## 2. Source hierarchy and reading map

| Source | Purpose |
| --- | --- |
| User's current instructions and accepted decisions | Scope, priorities and authorization |
| User-supplied HackMIT Maximor brief | Challenge: agentic reasoning, coordination/memory, consistency and human review; extraction alone is insufficient |
| [schooltrace/spec.md](schooltrace/spec.md) | Product and technical requirements; actual filename is lowercase |
| [schooltrace/ACCOUNTING_CONTROLS.md](schooltrace/ACCOUNTING_CONTROLS.md) | Financial invariants and accounting boundaries |
| [schooltrace/DATA_AND_EVALUATION.md](schooltrace/DATA_AND_EVALUATION.md) | Synthetic schemas, hidden truth, metrics and ablation |
| [schooltrace/INGESTION_PLAN.md](schooltrace/INGESTION_PLAN.md) | Proposed first implementation slice |
| [schooltrace/DEMO.md](schooltrace/DEMO.md) | Existing public-report + synthetic presentation; no replacement proposed |
| [WORKPLAN.md](WORKPLAN.md) / [IMPLEMENTATION_PLAN.md](schooltrace/IMPLEMENTATION_PLAN.md) | Team ownership, earlier time assumptions and cut list |
| [schooltrace/AGENT_PROMPTS.md](schooltrace/AGENT_PROMPTS.md) | Role behavior and response requirements |
| [contracts/README.md](contracts/README.md) | Shared API/UI bundle contract |
| This tracker | Current state, task IDs, decisions and next steps; not a second product spec |

Challenge brief provenance: user attachment `Pasted text.txt` in this conversation, read on 2026-09-19. Its relevant requirements are summarized above and in the ingestion plan; no provider/framework named in the brief is mandatory.

Read this tracker and the next task's relevant references first. Inspect actual files and Git status before editing. Do not treat planned file names below as files that already exist.

## 3. Current implementation evidence

Baseline inspected at `bc066ca`; updated below for the intake implementation. Re-check the current tree before editing.

| Area | Observed state | Evidence |
| --- | --- | --- |
| Dashboard | Eight tabs, two fixed workspaces, fixture-backed display and interactions | `web/src/app/`, `web/src/lib/data.tsx` |
| API | Health, bundle, approval-state mutation, reset; other demo actions 501 | `api/app/main.py` |
| Store | Legacy demos stay in memory; intake has SQLite originals, records, snapshots and events | `api/app/store.py`, `api/app/db.py` |
| Accounting | Allocation split, journal checks, reclassification and cash delta helpers | `api/app/accounting/money.py` |
| Tests | Intake, CFO triage, coordinator, review gates and accounting tests; current counts in latest checkpoint | `api/tests/` |
| Documents/import | Dynamic workspaces, CSV/text intake, mappings, validation, original evidence, coverage and evidence requests implemented | `api/app/ingestion.py`, `web/src/components/SourcesPanel.tsx` |
| Agents | Bounded OpenAI CFO triage with scoped tools, source citations, run persistence and dashboard projection | `api/app/agents/cfo.py` |
| Workflows | README and package marker only; real scenario workflows unimplemented | `api/app/workflows/` |
| Shared data | TypeScript/Pydantic mirrors and two demo JSON bundles | `contracts/`, `api/app/models.py`, `web/src/lib/types.ts` |
| Reports/learning | Fixture presentation, not real recomputation or measured learning | Dashboard data path and fixture contract |

Existing UI labels such as “Recorded run” are not proof of a saved real model run. Verify a replay manifest before claiming recorded agent performance. Current arithmetic helper tests do not establish all L01–L13 invariants or production readiness.

Pre-existing working-tree edits observed: `docs/design/prototype.html` and `web/bun.lock`. They belong to ongoing work and must be preserved. The intake implementation excludes those unrelated edits from its commit. Only intake-related paths and the planning/tracker documents are staged for the requested push.

## 4. Architecture to implement

Institution + scope + period
→ immutable uploaded sources and staged records
→ validated SQLite snapshot + exact accounting
→ provenance/context graph + typed retrieval/calculation tools
→ CFO coordinates AP, Payroll/Budget and Grants specialists
→ Internal Auditor checks original sources and calculations
→ human review
→ scenario recomputation + evidence-backed reports
→ reviewed playbooks reused in later periods.

Cross-cutting: explicit coverage, source versions, persisted task/decision events, access scope, honest execution mode, bounded model calls and separate private evaluation truth.

## 5. Repository map: existing and proposed modules

Every entry marked PROPOSED is a future responsibility, not a request to create folders or stubs. Keep implementation flat until extraction is justified; ingestion uses two Python modules and one UI component.

| Path | State | Responsibility |
| --- | --- | --- |
| `web/src/app/` | Existing | Eight product tabs |
| `web/src/lib/data.tsx` | Existing; extend | API state, workspace selection, polling, explicit fixture mode |
| `web/src/components/SourcesPanel.tsx` | Implemented | Upload, mapping preview, coverage, validation issues, evidence viewer |
| `web/src/lib/data.tsx` | Extended | Shared typed API helper; no extra source-client module |
| `api/app/main.py` | Existing; extend | API composition and integration |
| `api/app/models.py` | Existing; extend | Shared models and contract validation |
| `api/app/db.py` | Implemented | SQLite connection, transactions and additive version-2 schema; no migration folder |
| `api/app/ingestion.py` | Implemented | Parsers, mapping, validation, atomic commit and saved previews |
| Source functions in `api/app/ingestion.py` | Implemented | Immutable originals in SQLite, metadata, scoped spans and downloads |
| Coverage functions in `api/app/ingestion.py` | Implemented | Input readiness and review/unsupported gates |
| `api/app/store.py` / `ingestion.bundle` | Existing / implemented | Separate legacy demos and persisted empty intake bundles |
| `api/app/accounting/` | Helpers exist; expand | Ledger, schedules, exact calculations, lineage, invariants |
| `api/app/context/` | PROPOSED | Versioned nodes/edges, temporal retrieval and dependency invalidation |
| `api/app/agents/cfo.py` | Implemented | First OpenAI role, pinned evidence tools, schema validation, run limits and telemetry |
| `api/app/agents/grants.py` | Implemented | Grants & Compliance prompt and deterministic supplied-payroll award checks using shared runtime |
| `api/app/agents/auditor.py` | Implemented | Pinned preparer findings, fresh-source review, original CSV reperformance and exact-target verdicts |
| `api/app/cfo/`, `api/app/integrations/` | Merged from main | Separate coordinator/harness and intake bridge; live specialist/auditor adapters remain pending |
| `api/app/workflows/` | Placeholder | Close/payroll/AP/grants/audit-prep stages, evidence resumption and scenarios |
| `api/app/review/` | PROPOSED | Versioned human decisions, idempotent adjustment application |
| `api/app/memory/` | PROPOSED | Playbook proposals, applicability, replay-gate results, activation/retirement |
| `api/app/reports/` | PROPOSED | Snapshot-consistent reports and evidence exports |
| `api/tests/` | Existing; expand | Focused import, ledger, graph, authorization and integration checks |
| `contracts/` | Existing; extend | Bundle/import/tool contracts and safe developer fixtures |
| `api/data/` | Runtime, gitignored | One SQLite file stores database, original bytes and staging |
| Separate evaluator environment | PROPOSED | Held-out truth/generator/scorer, unavailable to runtime agent tools |
| `schooltrace/` | Existing | Product, accounting, agent, evaluation and implementation documentation |

The public-report workspace, synthetic baseline and approved synthetic scenario are separate contexts. Changes to one must not rewrite another.

## 6. Milestones and project backlog

Status vocabulary: EXISTING_PARTIAL, PROPOSED, READY, IN_PROGRESS, BLOCKED, VERIFIED, DEFERRED.
A task becomes VERIFIED only with concrete implementation and verification evidence. A checked-off plan is not implemented code.

| ID | Milestone / task | Status | Dependencies | Finish condition |
| --- | --- | --- | --- | --- |
| PLAN-01 | Review ingestion plan and project tracker | VERIFIED | User review | User approved implementation and push; flat structure requested |
| DATA-01 | Synthetic input pack, manifest, clean controls and lookalikes | EXISTING_PARTIAL | PLAN-01 | Importable starter pack exists; held-out truth/evaluation remains future |
| ING-01–05,07 | Source intake, validation, coverage and original evidence | VERIFIED | PLAN-01; DATA-01 | API checks and browser workspace/upload/commit/source walkthrough pass |
| ING-06 | Evidence request attachment and agent resumption interface | EXISTING_PARTIAL | Intake; future agent runtime | Attachment/event verified; live agent consumption not implemented |
| ACC-01 | Ledger, trial balance, opening/activity/closing and mappings | EXISTING_PARTIAL | ING-04 | Full scoped baseline and invariants tested |
| ACC-02 | Payroll/award/budget schedules and calculation lineage | PROPOSED | ACC-01, supporting inputs | Same snapshot totals tie; gaps visible |
| CTX-01 | Typed evidence edges and temporal retrieval | PROPOSED | ING-04 | Findings link to originals with provenance |
| CTX-02 | Transitive invalidation and projection version checks | PROPOSED | CTX-01, ACC-02 | Stale outputs cannot appear current |
| AGT-01 | Model adapter, structured roles, bounded tools and telemetry | EXISTING_PARTIAL | Intake | First CFO role verified with live OpenAI call; other roles and orchestration pending |
| AGT-02 | CFO → specialists → independent Auditor workflow | PROPOSED | AGT-01, ING-06 | At least three distinct investigations; unsupported claim revised/rejected |
| WF-01 | Evidence requests, resumable jobs and human queue | PROPOSED | ING-06, AGT-01 | Missing input blocks then resumes only affected work |
| REV-01 | Current-version, distinct-human, idempotent adjustments | PROPOSED | ACC-02, CTX-02, WF-01 | Approve once; coherent new snapshot; baseline preserved |
| WF-02 | Simulated AP payment preparation/release and holds | PROPOSED | REV-01, AP support | Bank-change items held; no real money moves |
| RPT-01 | Evidence-backed findings/report/export generation | PROPOSED | ACC-02, AGT-02, REV-01 | Every numerical claim cites a calculation/source |
| MEM-01 | Playbook proposal, replay gate, human activation | PROPOSED | AGT-02, evaluator boundary | Failed replay blocked; agents cannot activate memory |
| MEM-02 | Month-two reuse, exclusions, supersession/retirement | PROPOSED | MEM-01, October records | Logs show changed action and rejected stale precedent |
| EVAL-01 | Hidden findings scoring and consistency checks | PROPOSED | DATA-01, AGT-02, REV-01 | Saved measured metrics with denominators/limitations |
| EVAL-02 | Memory on/off comparison with identical current evidence/state | PROPOSED | MEM-02, EVAL-01 | Saved paired result; no private labels exposed |
| UI-01 | Replace fixture-only states throughout the dashboard | EXISTING_PARTIAL | Corresponding API milestones | Real state, failures, empty/stale states and source navigation |
| PUB-01 | Verified public-report manifest and evidence exploration | PROPOSED | Sources/spans; optional PDF/manual transcript path | Published values and units verified against originals |
| DEMO-01 | Real replay manifest, fresh-start setup and rehearsal | PROPOSED | Integrated demo path | Honest modes, reproducible run, explicit limitations |
| PILOT-01 | Authorized institution data, reviewed profile and access controls | DEFERRED | Separate pilot scope | Suitable handling for actual institutional records |
| EXT-01 | OCR/XLSX/connectors, complex accounting and broad deployment | DEFERRED | Core demo success | Separately scoped implementation |

Logical build order: scope/contracts → inputs/ingestion → accounting/evidence → agents/evidence requests → approvals/reports → memory/evaluation → integrated demo.
Evaluation fixtures and UI contracts can be prepared alongside their prerequisites; do not claim a milestone finished before its integration gate.

Do not automatically reuse the earlier 16-hour estimates. The ingestion addition needs re-estimation after contract review. If time is constrained, prioritize one complete evidence-gap investigation over adding more formats.

## 7. Team boundaries from the existing workplan

Proposed responsibility mapping; this is not a new assignment or permission to contact teammates.

| Workstream | Existing owner | Relevant work |
| --- | --- | --- |
| Functionality | Maxim | SQLite, import persistence/validation, exact accounting, approval/recompute, bundle builder |
| Workflows/data | Stanley | Raw synthetic packs, source documents, scenario definitions and private evaluation |
| Agent design | Nitya | Adapter, bounded tools, prompts, orchestrator and decision records |
| UI | hppddub | Sources/coverage flow, evidence drawer, live dashboard and states |

Source schema and endpoint contracts affect all four tracks. Record contract changes and required consumers; coordinate before merging. Stay within the current task and preserve others' local edits.

## 8. Decision register

| ID | Decision | State / reason |
| --- | --- | --- |
| D-01 | Educational AI auditor with evidence-backed findings and independent review | User direction; align CFO framing around audit preparation |
| D-02 | Institution-neutral intake | Explicit user clarification; no named-school implementation |
| D-03 | Planning review completed; intake code and push authorized | Subsequent explicit user instruction |
| D-04 | CSV and TXT/Markdown first; PDF extraction later | Approved and implemented |
| D-05 | SQLite includes original bytes as BLOBs; atomic synchronous import | Implemented to keep folders/services small |
| D-06 | Sources & coverage inside existing navigation | Implemented; eight tabs retained |
| D-07 | Synthetic transaction demo, public sources separate | Existing spec boundary; real private data deferred |
| D-08 | Readiness per capability, not “all files uploaded = clean audit” | Proposed operationalization of spec completeness |
| D-09 | Model/provider ID verified when adapter is implemented | Existing named model is a spec target, not evidence of integration/availability |
| D-10 | Learning means reviewed playbooks and measured behavior change | Spec §7.4; no unreviewed prompt self-editing |
| D-11 | Consistent names and accounting basis across demo/profile | Open integration detail; do not present a fictional university using a demo district basis as statutory university accounting |

Approved decisions and implementation simplifications are recorded in ingestion plan §§15–16. Do not ask Max to decide routine file/function names; request direction only on material product scope.

## 9. Acceptance and challenge alignment

| Requirement | Concrete demonstration | Owning tasks |
| --- | --- | --- |
| Actual documents/data drive multi-step work | Missing service evidence → upload → source citation → recalculation → revised finding | ING, AGT, WF |
| Coordinated roles and independent challenge | Three specialists plus Auditor rereading originals; not agreement-only voting | AGT-02 |
| Consistency across financial outputs | One approved adjustment updates dependent schedules/reports with cash unchanged | ACC, CTX, REV, RPT |
| Human review when uncertain | Targeted evidence request and distinct human adjustment approval | WF-01, REV-01 |
| Memory changes what happens next | Approved precedent alters logged task actions; changed contract defeats stale memory | MEM-01–02 |
| Own measure of improvement | Held-out precision/recall, evidence-gap accuracy, consistency and paired ablation | EVAL-01–02 |
| Honest demo | Scripted/recorded/live labels match saved manifests; example metrics stay labeled | DEMO-01 |

Keep spec AC-01–15 as the full acceptance checklist. Link actual evidence here as tasks finish; do not reduce passing acceptance to UI appearance.

## 10. Implementation card template

Copy this section for the next active task only; avoid duplicating the whole spec.

### TASK-ID — title

- Status:
- Goal / user-visible result:
- Owner:
- Spec sections / acceptance IDs:
- Depends on:
- Files inspected:
- Files allowed to change / likely new files:
- Contracts affected and consumers:
- Key decisions / unresolved assumptions:
- Implementation notes:
- Verification performed (command or browser steps, result, date):
- Remaining failure / blocker:
- Next smallest step:
- Commit or working-tree evidence:
- Handoff note:

No secrets, raw private financial records or hidden grader answers belong in this tracker.

## 11. Context and handoff protocol

At the start of a work session:
1. Read §1, §3, §6, decision register and latest checkpoint.
2. Check current branch, HEAD and dirty files. Reconcile code against the last recorded state.
3. Read the selected task's spec sections, applicable AGENTS.md and source modules.
4. Choose a bounded implementation slice and state its completion evidence.

After a meaningful slice or before a context handoff:
1. Update task status based on what exists and was verified, not intended progress.
2. Record exact changed files, contract decisions, test results, unresolved failures and next action.
3. Link a commit if one exists; otherwise describe working-tree changes accurately. Do not commit simply to fill this field.
4. Keep the active summary under roughly 30 lines. Archive lengthy completed notes only when they make this file hard to scan.
5. Preserve user approval state. A new session or context window is not permission to start code while review is pending.
6. Keep evidence in files/manifests and concise summaries here; do not rely on chat memory or store private chain-of-thought.

### Planning checkpoint — 2026-09-19 (superseded by implementation below)

- Objective: plan ingestion and a whole-project implementation/context tracker.
- User clarified: specific-school mention was an analogy; use institution-neutral design.
- Source baseline: `max` / `bc066ca`.
- Existing app: fixture dashboard + in-memory API + small money library.
- Existing local changes: prototype HTML and Bun lockfile; preserve.
- Added: `schooltrace/INGESTION_PLAN.md` and `PROJECT_TRACKER.md`.
- Code/dependencies: no new implementation in this turn.
- Verification: all local Markdown links resolve; scope/spec consistency reviewed; no named-school design remains. No application tests needed for these documentation-only additions.
- Scope proposal: CSV + text evidence, immutable sources, SQLite, reviewable import, capability coverage, dynamic workspaces and evidence requests.
- Current blocker: user explicitly requested plan review before coding.
- Next action: receive Max's review, amend these documents, then implement only the accepted scope.
- Next coding task if approved: ING-01, source/coverage contracts and minimum synthetic input manifest.
- Do not: specialize to a real school, treat sample labels as live agents, or claim prototype tests validate the whole system.

### Latest implementation checkpoint — 2026-09-19

- Authorization: Max approved intake implementation and push to current branch; requested few folders.
- Branch: `max`; unrelated prototype and Bun lockfile edits are excluded from staging.
- Added backend modules: `api/app/db.py`, `api/app/ingestion.py`; no extra module directories.
- UI: `SourcesPanel.tsx` within Command center, dynamic sidebar workspaces, safe empty API state.
- Persistent data: gitignored SQLite stores immutable originals, staged previews, record versions, snapshots, evidence requests and local events.
- Supported files: CSV / UTF-8 TXT / Markdown. Templates are in `contracts/fixtures/intake.json`.
- Verified: upload, mapping, exclusion, exact amounts, journal/opening validation, identity conflicts, reimports, versioned commit, rollback, scoped citations/downloads and evidence attachment.
- Tests: 49 backend checks; TypeScript/production build; lint of changed frontend files.
- Browser: created a fictional September workspace, imported starter pack, committed and opened original ledger lines; stored data persists across clients/connections.
- Deliberate simplification: bounded synchronous transactions instead of a worker queue. Previously staged imports survive; interrupted transactions roll back.
- Partial: ING-06 records an evidence-supplied resumption event; no agent runtime exists to consume it yet.
- Not implemented: PDF/OCR/XLSX, private institutional access, complete management reports, agent orchestration, scenario recomputation, memory or measured evaluation.
- Next implementation milestone: accounting/query tools plus one real specialist and independent auditor consuming these source/snapshot IDs.
- Handoff: no secrets or private real records were added; do not mistake input readiness for a completed audit.

### CFO triage implementation and review checkpoint — 2026-09-19

- User approved: update hybrid-model/learning spec, work on `max`, build first OpenAI agent; training later.
- Spec now separates run state, reviewed institutional memory and offline versioned model adapters.
- LangGraph is the selected future orchestrator; this first role uses a bounded synchronous loop.
- Local extraction target: benchmark NuExtract3 4B, constrained schema, Pydantic, offline LoRA; none downloaded/trained yet.
- First agent: `api/app/agents/cfo.py`; no new service or folder hierarchy. API routes and existing source panel expose runs.
- Review fixes: historical snapshot reads, full-ledger totals beyond 100 rows, record pagination, exact citation validation,
  server-side argument checks, actual tool-call/time/token limits, retained tool outputs on failure, sanitized provider errors,
  idempotent request IDs, stale-start rejection, abandoned-run recovery and honest unreviewed finding statuses.
- Config: backend auto-loads ignored `api/.env`; the user provided a key and authorized local persistence. No key in tracked files.
- Tests before main integration: 58 backend checks; production Next.js build/TypeScript and changed-file lint passed.
- Live provider check: isolated synthetic September pack; gpt-5.4-mini completed 8 tool calls, 15,999 tokens,
  cited missing service evidence. The temporary test database was discarded after verification.
- Browser review caught cents/dollars confusion and unread evidence described as absent. Added bounded source previews,
  explicit units and a supplemental currency-prefixed amount guard (not semantic validation of all monetary prose).
- Corrected live run: 8 tool calls, 37,175 tokens; identified the synthetic payroll/service allocation conflict,
  used the correct 10,000.00 charge and 50,000.00 ceiling, and preserved unreviewed statuses. Original citation opens in UI.
- Deferred: independent auditor, specialist execution, durable LangGraph scheduling/resumption, automatic evidence continuation,
  full financial reports, local extraction model, training, playbooks and measured learning.
- Keep pre-existing prototype HTML and Bun lockfile edits untouched. User authorized pushing `max` and merging into `main`.
- Main integration: incorporated `f3d8314`, preserving the separately merged coordinator/harness. Resolved `main.py`
  by keeping both routers, dotenv loading and coordinator shutdown; regenerated the merged uv lock.
- Combined tree: 92 backend tests (including cross-route coexistence), production build/TypeScript,
  changed-file lint and `uv lock --check` passed. Live provider and original-citation browser checks passed.
- Next integration task: implement real specialists and auditor behind coordinator ports, then explicitly unify
  triage/task dispatch and run history. Do not describe scripted coordinator results as live independent review.

### Grants & Compliance implementation checkpoint — 2026-09-19

- User requested the next live agent; implemented locally on `max`, after the prior CFO merge `d1d0f18`.
- New module: `api/app/agents/grants.py`. Reuses the existing bounded OpenAI loop, snapshot tools,
  citation validator and run persistence; no new service, dependencies or directory hierarchy.
- Added allowlisted request agent (`cfo` default / `grants_compliance`); role-aware idempotency,
  one active snapshot agent per workspace, history capped per role, and optional `GRANTS_MODEL`.
- `check_grant` computes full pinned payroll-subset totals, inclusive service windows and ceiling
  comparisons; missing/ambiguous awards stay unknown. Ledger/payroll are never added together.
- UI: existing SourcesPanel selector, exact role names, separate results, source-citation modal and
  evidence requests. Findings/Reasoning preserve both roles; CFO briefing is not overwritten by Grants.
- Verified: 105 backend tests, production build/TypeScript, changed-file lint, whitespace checks.
- Real synthetic-data OpenAI run: 7 tool calls / 35,509 tokens; caught full-cost grant charging versus
  60/40 service evidence, requested allocation terms, and did not invent an adjustment. Validation
  rejected two intermediate submissions before accepting corrected output. Citation opens original;
  switching roles retains CFO's earlier result. No private institutional records used.
- Known limits: supplied payroll only, not lifetime grant spend or legal eligibility certification;
  citations verify text/location, not inference. Independent Auditor and automatic coordinator dispatch
  remain pending; neither local extraction nor training was added.
- Updated spec §8.2, API/shared contracts and READMEs. This new Grants work is uncommitted/unpushed.
  Pre-existing prototype HTML and Bun lockfile edits remain unchanged; the API key is still ignored.

### Internal Auditor implementation checkpoint — 2026-09-19

- User authorized building the Internal Auditor and pushing to main; includes the pending Grants slice.
- Added `agents/auditor.py`, sharing the bounded API loop but with its own prompt, schema and tool state.
- Pins current-snapshot preparer run/finding IDs; no self-review, foreign targets or uncited acceptance.
- Accept/reject requires explicit fresh reads of all target citations. Accept also requires supporting
  calculations inferred from cited financial record roles and preparer tool history. Original CSV bytes
  are reparsed and reconciled with pinned records before arithmetic; mismatches block acceptance.
- Four verdicts per run; unreviewed IDs/counts are explicit. Further runs prioritize unreviewed targets.
  Latest per-finding verdicts from the last 20 completed audits are preserved. Preparer reruns never
  inherit old verdicts; same-snapshot target staleness is exposed in the UI.
- UI selector, exact-target verdict cards/citations, dashboard annotations and optional AUDITOR_MODEL.
  Candidate statuses and human approval stay separate; no blanket verified flag or financial mutation.
- Live synthetic test: first attempt correctly refused un-retrieved citations then hit its budget.
  Improved exact missing-line feedback and removed preview text from Auditor context. Corrected run
  completed 9 tool calls / 36,369 tokens, reviewed 4 of 6 findings: two bounded acceptances and two
  needs-evidence verdicts, with fresh reads and independent grant/ledger reperformance.
- Verification: 114 backend tests, production build/TypeScript, changed-file lint, whitespace checks,
  real provider run and browser source-citation check passed. Ready to push combined Grants/Auditor
  changes from `max` to `main`; no upstream divergence at the final fetch. No private institutional
  records used; local API key remains ignored and pre-existing prototype/Bun edits remain untouched.
- Limitations: shared parsing/math implementation is not algorithmic independence; semantic model
  mistakes remain possible. No audit opinion, compliance certification, automatic coordinator adapter
  or local-model training. AP and Payroll specialists remain unimplemented.
