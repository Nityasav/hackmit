# Sherlock — documents and financial records implementation plan

Status: APPROVED — intake implementation delivered; agent integration remains a later milestone.
Prepared: 2026-09-19. Repository inspected: branch `max`, commit `bc066ca`.
Canonical location: `schooltrace/INGESTION_PLAN.md`.
Related tracker: [PROJECT_TRACKER.md](../PROJECT_TRACKER.md).

## 1. Product and source of truth

Sherlock is an AI-agent auditor and audit-preparation assistant for education systems. It investigates financial records, traces conclusions to evidence, asks for missing records, and routes proposed corrections through human review. The CFO and specialist roles organize this work; the Internal Auditor independently checks it. It does not issue a professional audit opinion.

The user-supplied **HackMIT 2026 Maximor track brief** is the challenge reference. Its central requirements are multi-step reasoning over documents and data, coordination or memory that changes actions, consistency across workflows, and human review under uncertainty. Uploading and extracting files is the first foundation, not the finished competition entry. The brief explicitly permits invented institutions and data; a synthetic school is a valid development setting.

Local source attachment read for this plan: `/Users/max/.codex/attachments/cb290235-a839-4a35-9167-3dea3290d803/Pasted text.txt`. This path is local provenance, not a dependency required to run the project.

Project requirements:
- [spec.md](spec.md) §§1–4: educational audit preparation, institution/profile selection, import, completeness, baseline.
- [spec.md](spec.md) §§5–8: storage, provenance, exact money, graph, typed tools, reviewer roles.
- [spec.md](spec.md) §§9–13: consistent reports, uncertainty, interface, failure handling, acceptance criteria.
- [ACCOUNTING_CONTROLS.md](ACCOUNTING_CONTROLS.md) §§1–3: institution boundaries, invariants, no double counting.
- [DATA_AND_EVALUATION.md](DATA_AND_EVALUATION.md) §§1–3: runtime input schema, synthetic data, private evaluation labels.
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) and [WORKPLAN.md](../WORKPLAN.md): existing team split and time cuts.

This document records the approved design. Max subsequently authorized implementation and pushing to the current branch, with a preference for fewer folders. Implementation choices and remaining boundaries are recorded below.

## 2. Do we need all of an institution's financials?

We need a defined reporting question, a defined population and period, and enough evidence for the resulting claims. “All financials” is too vague to be an import requirement.

| Intended output | Minimum supporting input | If it is absent |
| --- | --- | --- |
| Explain a published budget or annual report | That report, its period/entity/units, cited pages or rows | Ask for the source; do not invent values |
| Investigate selected purchases | Invoice records, POs/receipts where applicable, approval policy and approvals; ledger/payment links for posting/payment claims | State what was tested and request missing support |
| Investigate payroll charged to a grant | Payroll allocation, applicable award terms, actual service/allocation evidence; ledger link to test posting | Can identify unsupported allocation; cannot confirm a correction amount without the allocation evidence |
| Compare actual spending with budget | Approved budget version and scoped actual ledger activity, matching periods and dimensions | Budget-only explanation; no actual-spend or variance claim |
| Produce a management close package | Validated opening trial balance, chart/mappings, complete balanced activity for the ledger scope, and relevant control schedules | Scoped preliminary analysis with explicit blockers; no complete statements |
| Claim institution-wide audit coverage | Defined population, verified coverage, applicable policies, review, and supporting records across that scope | No claim of comprehensive coverage or a clean audit |

A balanced trial balance is an arithmetic check; it does not prove completeness or proper classification. A sample of receipts is not an institution's full books.

### How an institution supplies its records

The product must support any school, district, board, or university. No specific real institution is the implementation target.

1. Identify the reporting entity and investigation scope: a whole institution, a school/campus, a department, a grant or selected transactions. Record the period and question before requesting files.
2. For public-document exploration, obtain published budgets, statements or reports from the institution's official publications. Record the actual entity, report year, currency and units. Public reports provide context but do not establish access to underlying transaction records.
3. For transaction work, the institution's authorized finance user exports the relevant data from its accounting/payroll/procurement systems. The user identifies the record custodian and available scope; the app must not assume the school office holds every record.
4. Request chart of accounts/dimension definitions, export filters, row counts and control totals alongside each export. Request support required by the selected investigation, rather than unrelated personal information.
5. Record centrally managed expenses, payroll, assets, funding, shared services, and transactions excluded from a school/campus-only extract. Do not allocate parent-organization totals to a school without an evidenced allocation rule.
6. Keep consolidated reports labeled as consolidated. A school-level budget is not automatically school-level actual spending or a standalone balance sheet.
7. If internal records are unavailable, offer public-document mode. Invented transactions are restricted to private evaluation inputs and are always labeled synthetic.

Suggested request pack: “For [entity/cost-centre], [start/end dates], and [investigation], please provide CSV exports of relevant ledger/transaction records with stable IDs, account/dimension definitions, currency, export filters, row counts and totals; applicable budgets/award terms/policies; and evidence for the transactions in scope. Please identify missing systems, central costs and exclusions.”

No request is sent as part of this plan. Private institutional data is not assumed available. Institution type, jurisdiction, accounting basis and currency are explicit configuration: changing a name or currency does not make one management profile applicable to a different institution. Public/private universities and schools in different jurisdictions require separately reviewed accounting profiles (spec §3.1).

## 3. Recommended scope for the first build

Build a **Sources & coverage** flow inside the existing Command center, with a shared evidence drawer reachable from Findings, Approvals, and the Agent board. Retain the eight top-level tabs.

Three data contexts must remain separate:
- **Synthetic evaluation:** developer-created records used only by tests and held-out benchmarks.
- **Public report exploration:** published reports and explicitly extracted statements; no invented underlying transactions or writable financial scenario.
- **Authorized institutional investigation:** future pilot; requires actual access, an institution profile and appropriate handling of its records. Not part of the initial hackathon dataset.

First upload formats:
- CSV for structured financial records.
- UTF-8 TXT and Markdown for terms, service records and other evidence, with line locators.
- Text PDF extraction is a separately estimated follow-up. Existing PDFs can be retained as originals with a human-reviewed, page-linked transcription; label this manual, not automated extraction.
- XLSX, scanned PDFs/OCR, images, email archives, ZIP archives, cloud-drive sync and live ERP/bank connectors are deferred. Unsupported formats get a clear message, not an empty successful import.

Manual CSV export is the initial spreadsheet path. Original-to-transcription links must be preserved; do not silently flatten a PDF or lose page references.

Keep model calls out of deterministic financial import and validation. Later, an agent may suggest document type or mappings, but a user confirms ambiguous mappings and authoritative amounts come from validated records.

## 4. User experience

1. Choose or create an institution/workspace and select period, currency, accounting profile and investigation scope.
2. Open Sources & coverage. See requested source types, coverage status and existing uploads.
3. Upload multiple files and tag each file's role: opening balances, GL activity, payroll, budget, policy, grant terms, service evidence, or other supporting document.
4. Preview detected columns/text and confirm mappings, date format, amount units, debit/credit convention, source system and record identity.
5. Review counts and totals, rejected rows, unmapped accounts, period gaps, conflicts and duplicates. Each issue links to the original location and states what it blocks.
6. Confirm the valid staged dataset. The server atomically publishes a new immutable snapshot. Import confirmation is separate from approving an accounting adjustment.
7. Choose an available investigation. Missing support can permit a bounded evidence-gap investigation; missing core ledger controls blocks final statements.
8. When an agent requests a service record, upload through that request. Preserve the request/task link; resume the affected task against a new source/snapshot version after validation.

Coverage states: `missing`, `processing`, `needs_review`, `partial`, `ready_for_scope`, `unsupported`. Display required source types and periods plus accepted/rejected counts and control totals. Do not label a workspace “audit complete” from a file count or an opaque percentage.

If the API is unavailable, workspaces show an offline/error state with any cached snapshot explicitly dated. They must never substitute unrelated data.

## 5. First data pack and normalization contract

Build import support incrementally: core financial spine, then the payroll/grant evidence path, then AP and budgets. [DATA_AND_EVALUATION.md](DATA_AND_EVALUATION.md) §2 remains the broader schema reference.

| Source | First normalized fields | Purpose |
| --- | --- | --- |
| Institution configuration | ID, name, entity type, jurisdiction, currency/minor-unit scale, fiscal calendar, profile/version, included schools/cost centres | Bound every query/report |
| Chart of accounts | Code, name, type, normal balance, report mapping, effective dates | Validate mappings |
| Opening trial balance | Account/dimensions, balance date, debit/credit | Establish supported opening state |
| General ledger | Entry ID, line ID, accounting date, account, debit/credit, school/fund/award dimensions, source-record ID/version | Baseline financial events |
| Payroll | Payroll-line ID, synthetic staff ID, service/pay periods, gross/deductions/net/employer costs, award allocation, ledger link | Allocation investigation |
| Grant register | Award ID, ceiling, currency, validity dates, policy/source reference | Scope eligible costs |
| Documents | Original bytes, type, hash, issuer, applicable period, text spans, source version | Terms, allocation/service evidence and counterevidence |
| Budget (next slice) | Approved version, period, account/dimensions, amount, approval reference | Budget-versus-actual |
| AP support (next slice) | Invoice/line/vendor ID, amount, service/due dates, PO/receipt IDs and quantities, approval links | Duplicate and three-way-match tests |

All financial records inherit institution, currency, period, source ID, source locator and batch ID. Preserve original strings as well as normalized values. Import money as decimal strings converted exactly to integer minor units; reject unsupported precision and ambiguous currency/units. Store dates by meaning, not in one interchangeable date field.

A school-cost-centre export may omit the other side of central journals. Do not manufacture balancing lines. Require complete journals for ledger publication, or store the extract as a scoped transaction dataset eligible only for explicitly bounded analysis.

If no existing ledger is supplied, document import does not reconstruct one automatically. Reconstruction is a later reviewed-proposal workflow requiring supported opening balances and event identity.

## 6. Storage and provenance design

Use SQLite plus local immutable originals for the hackathon, as planned in spec §5. Keep the schema portable and place monetary arithmetic in `app/accounting/`. No vector database is required for the first evidence path.

Proposed entities (names are design targets, not existing tables):
- `institutions / workspaces / periods / accounting_profiles`: scope, capability and version.
- `ingestion_batches / ingestion_files / import_jobs`: lifecycle, uploader, status, errors, parser/version, checkpoint.
- `source_documents / source_versions / source_spans`: hash, media type, storage key, issuer, dates, classification, original location, extraction method.
- `staged_records / mapping_versions / validation_issues`: raw values, normalized preview, row/field errors, mapping decisions.
- `accounts / opening_balances / journal_entries / journal_lines`: accepted, versioned baseline.
- `payroll_lines / awards`, later `budgets / invoices / purchase_orders / receipts / approvals`: corroborating records linked to ledger events.
- `snapshots / snapshot_sources / calculations`: exact input versions, scope, mappings, ledger revision and outputs.
- `evidence_links / graph_nodes / graph_edges`: record-to-source and dependency edges with assertion class, provenance, valid time and recorded time.
- `evidence_requests / review_decisions / audit_events`: who requested/reviewed what, when and why.

Every accepted fact must be traceable: normalized field → original source version → row/line/page → immutable bytes. A hash proves which bytes were used, not whether the content is true.

Proposed local layout: a gitignored `api/data/` directory containing the SQLite database and generated storage keys under `sources/`; never serve it as a static public directory. Keep evaluation truth outside runtime-accessible paths. Before implementation, add ignore rules for originals as well as databases.

MVP execution: persisted job records with a small single-worker queue/runner and checkpoints; avoid losing state in process-only background tasks. Upload returns a batch/job ID, the UI polls status. On restart, resume or explicitly mark interrupted work retryable; never mark a half-import complete.

## 7. Import lifecycle and validation

Batch lifecycle: uploaded → parsing → needs_mapping → validating → ready_to_commit → committed.
Failures branch to `failed` or `needs_review`; retry creates a new attempt without destroying history. File-level parse status and row-level validation remain visible separately.

1. Validate file size/type/content, assign a generated storage key, hash and preserve original bytes.
2. Parse in staging with bounded limits. Record exact row/line positions, parser version and warnings.
3. Confirm mapping against the chosen institution, profile and schema. Explicitly resolve ambiguous dates, signs and amounts.
4. Validate required fields, exact money, IDs, account effective dates, periods, currencies and cross-record references.
5. For GL publication, enforce complete balanced journals, supported opening balances and mapping completeness. Missing external corroboration becomes an evidence gap; invalid ledger structure blocks ledger commit.
6. Present a versioned preview and its digest. Human commit references that exact version.
7. Commit accepted records, source manifest and snapshot in one database transaction. A stale preview gets a conflict response and must be revalidated.

Default: no silent partial commits. Invalid files can be excluded explicitly, with exclusions recorded and coverage recalculated. Never import half a journal or drop bad rows while retaining a “complete” label. Raw quarantined material is not authoritative ledger state or normal agent retrieval content.

Validation must show: parsed/accepted/rejected/duplicate row counts; raw and accepted debit/credit totals; distinct IDs; min/max dates; source-stated counts/totals when supplied; differences; missing accounts and references. User-declared scope without independent control totals is labeled unverified coverage.

## 8. Reimports, revisions and double counting

Use two distinct controls:
- Byte deduplication: scoped source hash finds repeated file content. Same bytes can be linked to another evidence request without creating duplicate financial events.
- Record idempotency: spec §6 key `(institution, source_system, source_record_id, source_version)`. For GL lines, identity includes stable entry/line identity.

Same record key + same canonical payload is a no-op. Same key + different payload is a conflict. A new source version creates a staged superseding record and diff; the old version stays queryable. Different row order or filenames must not duplicate stable source records.

If stable IDs are absent, request a reviewed mapping or scope an assigned row identity to that immutable file; disclose that cross-export matching is unverified. Similar date/amount/vendor is a duplicate candidate, never an automatic deletion rule.

Keep evidence identity separate from economic-event identity. The invoice, bank payment, payroll export and ledger line can describe the same event; they do not each become new expense postings. Corroborating records link to the baseline. Uncertain matches stay unresolved.

A new committed version marks dependent calculations, tasks, proposed adjustments, graph projections and reports stale. Recompute from explicit snapshot versions; do not rewrite a previous report. An in-flight task may finish against its pinned snapshot, but its result must be marked superseded before publication as current.

## 9. Readiness and missing-evidence rules

Store readiness per capability and scope, with machine-readable blocker codes and source/period references:
- `document_explanation`: readable source, known entity/period/units and valid locators.
- `transaction_investigation`: identifiable records plus stated population and applicable criterion. Missing supporting documents yields “needs evidence,” not automatic wrongdoing.
- `payroll_allocation_confirmation`: payroll amount/allocation, applicable award terms, verified current service evidence and deterministic calculation.
- `management_statements`: supported profile, opening trial balance, complete balanced activity, valid mappings and matching snapshot/control totals.
- `budget_variance`: comparable actuals plus approved budget/version and consistent scope.
- `scenario_adjustment`: supported accounting state, current proposal, independent review and distinct human approval.

Backend enforces these rules; disabled UI buttons alone are insufficient. Gaps include absent exports, missing service records, quarantined amounts, unsupported account classes, unknown units/currency and mismatched periods. “Not applicable” requires a recorded scope reason.

Source sufficiency can grow over time. Adding the missing service record changes readiness and opens targeted work; it does not require restarting unrelated completed investigations.

## 10. API and frontend integration

Proposed routes, all scoped to a validated workspace:

| Route | Contract |
| --- | --- |
| POST /api/workspaces | Create a synthetic/public workspace with explicit institution/profile/scope |
| POST /api/workspaces/{ws}/imports | Stage bounded multipart files plus source roles/metadata; return batch/job ID |
| GET /api/workspaces/{ws}/imports/{id} | File/row statuses, preview, mappings, validation and counts/totals |
| PATCH /api/workspaces/{ws}/imports/{id}/mapping | Versioned mapping confirmation; revalidate |
| POST /api/workspaces/{ws}/imports/{id}/commit | Expected preview version + idempotency key; return snapshot and coverage |
| GET /api/workspaces/{ws}/coverage | Per-capability readiness and missing evidence |
| GET /api/workspaces/{ws}/sources/{id} | Metadata and authorized original download |
| GET /api/workspaces/{ws}/sources/{id}/spans/{span} | Original locator, extracted content, validation status |
| POST /api/workspaces/{ws}/evidence-requests/{id}/responses | Attach a source/batch to the request; validation precedes task resumption |

Use structured errors with `code`, `message`, `batch_id`, `source_id`, `locator`, `blocking_capabilities`, `retryable`. Conflict/staleness, unsupported formats, size limits and validation failures have distinct HTTP/error codes.

Existing `GET /api/workspaces/{ws}/bundle` stays the dashboard seam. Add compact coverage/source summaries and identifiers, not original document bytes or full raw payroll rows. Source detail is fetched on demand.

Workspace IDs are validated persisted identifiers. Keep data origin (`synthetic/public/authorized` when enabled) separate from execution mode.

Update `contracts/README.md`, `api/app/models.py`, `web/src/lib/types.ts` and representative fixtures together with explicit contract-version compatibility. Coordinate affected workstreams before merging; do not silently break other contributors' fixtures. New empty workspaces must display empty state, not recorded findings.

## 11. Agent handoff: how import becomes an audit

The ingestion slice exposes validated evidence; the next slice uses spec §8 tools.

- CFO Agent receives coverage plus the question and chooses bounded specialist tasks.
- Payroll & Budget reads payroll and asks the deterministic engine to calculate; it cannot invent the supported allocation.
- Grants & Compliance checks the actual award clause and service period and requests missing evidence.
- AP & Payments tests duplicate candidates against distinct receipts/POs rather than simply matching amounts.
- Internal Auditor independently rereads originals, repeats calculations and accepts, rejects or requests evidence.
- Human reviews any adjustment; agents cannot use the import endpoint as a shortcut to approving financial changes.

Tools accept source IDs, allowed query templates and snapshot IDs; never unrestricted paths or arbitrary SQL. Record tool input hashes, output references and concise decisions. New documents trigger a bounded resumption against the new snapshot with a logged reason.

Proving this later slice matters: a novel service record supporting 80/20 must yield a different calculation from 60/40; a missing record must remain unresolved. Do not implement filename-to-answer lookups. A deterministic parser is appropriate; predetermined investigative conclusions are not.

## 12. Local file handling and access boundaries

For the local synthetic/public MVP:
- Bind development services to loopback; record a configured local human reviewer identity, distinct from agent identities. This is not production authentication.
- Proposed configurable limits: 20 files/batch, 10 MB/file, 50 MB/batch, 50,000 rows/file. Enforce during upload and parse; report limits before submission.
- Validate media signatures/content where applicable; reject path traversal, executables, archive uploads and malformed/over-limit files. Generated storage keys never use a client path.
- Render text safely and download unknown originals as attachments. Never execute document content, macros, links or embedded instructions.
- Treat document instructions as data. Uploaded text cannot change permissions, approve itself or access secrets/evaluator truth.
- Source reads and downloads enforce workspace/snapshot scope; redact sensitive values from telemetry.
- No automatic remote URL fetching in the first build. A user supplies the file and optional provenance URL.
- Private institutional data remains out of local-only deployments until access, storage/retention, reviewer authentication and model-transmission rules are agreed for that pilot.

These are import requirements from spec §12, not claims that the prototype is suitable for production school records.

## 13. Implementation sequence after review

| ID | Deliverable | Depends on | Completion evidence |
| --- | --- | --- | --- |
| ING-01 | Freeze source/coverage contracts and small synthetic input manifest | Plan approval | Contracts/mirrors/fixtures consistent; profile and scope explicit |
| ING-02 | SQLite migrations, originals store, batch/job staging | ING-01 | Restart retains sources/jobs; workspace isolation verified |
| ING-03 | CSV + TXT/Markdown parsing, mappings and exact validation | ING-02 | Located errors; source totals and normalized preview agree |
| ING-04 | Idempotent commit, snapshot manifests, provenance and invalidation hooks | ING-03 | Reimport no-op, revision conflict/supersession, atomic failure tests |
| ING-05 | Sources & coverage UI, empty states and evidence drawer | ING-01–04 for end-to-end verification | Upload/preview/review/commit/source-open flow works in browser |
| ING-06 | Evidence request attachment and readiness-driven task resumption interface | ING-04–05, agent task interface | Missing-to-supplied evidence transition preserves task/source history |
| ING-07 | Pilot of the full ingestion acceptance scenario | ING-01–06 | Saved test results and manual walkthrough; no fixture leakage |

UI work can use agreed contracts before the API is finished. This is a workstream dependency plan, not authorization to spawn agents or contact teammates.

Do not promise the existing 16-hour schedule still holds after adding arbitrary uploads. Re-estimate after ING-01. If time is tight, finish one CSV + Markdown payroll investigation path before adding parser formats or more workflows.

## 14. Acceptance scenario and test matrix

Scenario: create a fictional school workspace; upload chart, balanced opening/GL, payroll and grant terms for September; intentionally omit the service record. Preview/mapping/commit produces a scoped baseline with a missing-evidence item. An investigation can request evidence but cannot confirm the allocation. Add the service record through that request, open its exact lines, and resume the agent path. A later human-approved scenario reclassifies expense without changing cash.

Ingestion must be independently testable before real agents exist; mark the agent-dependent end-to-end portion blocked until that integration is implemented.

| Check | Expected result | Spec coverage |
| --- | --- | --- |
| Same file twice; renamed/reordered export with stable IDs | No second financial event | AC-01, §6 |
| Same ID/version with changed amount | Conflict, no silent overwrite | §6 |
| New source version or changed policy | Preserved old snapshot; dependent outputs stale | AC-11, §7.5 |
| Crash mid-import; retry commit twice | No partial journal/snapshot; one committed effect | AC-01–03 |
| Unknown account, currency, ambiguous dates or unbalanced journal | Quarantine/block correct capability with original locator | AC-02, §12 |
| GL plus matching invoice/payment documents | One ledger event with corroborating evidence | §4, controls §3 |
| School-only extract omits balancing legs | Scoped data mode, no fabricated balancing journal | §3, AC-02 |
| Missing opening balance vs missing receipt | Statements blocked vs bounded evidence-gap investigation | AC-09 |
| New workspace and API failure | No synthetic findings leaking into real/public workspace | §12 |
| Cross-workspace source ID or raw path request | Denied | AC-10 |
| Document says “approve me” | Treated as source text; no privilege/action change | AC-10 |
| Click a source citation | Correct immutable row/line/page and version | AC-05 |
| 60/40 vs 80/20 later agent integration | Exact 4,000 vs 2,000 reclassification on 10,000; cash unchanged | AC-04–06 |
| Failed or low-quality parsing | Visible error/review state, not empty successful import | §12 |

Add focused parser/service/API tests and one meaningful browser walkthrough; retain existing accounting tests. Measure import duration on the stated fixture size; the existing under-30-second target is a target, not an observed result.

## 15. Decisions proposed for Max's review

1. **Start with synthetic education records and manual uploads.** Design institution-neutral intake; do not wait for inaccessible internal records.
2. **CSV + TXT/Markdown first.** PDF text extraction is a follow-up; OCR/XLSX/connectors remain deferred. This follows the compressed workplan's parser cuts while making document intake real.
3. **Use Sources & coverage within existing tabs.** No ninth top-level tab.
4. **Add dynamic workspaces, persistent sources and SQLite now.** These extend the current two-workspace fixture contract and must be coordinated with the team.
5. **Build source-to-evidence-to-investigation as the first complete feature.** Do not stop at an uploader; follow with a real specialist/auditor evidence-gap interaction.
6. **Preserve separate identities/profile labels.** Synthetic evaluation data and a real institution are not interchangeable accounting entities. Label the supported accounting basis explicitly.

Review outcome: APPROVED by Max in the conversation.
Approved scope / changes: implement intake and push to branch; keep code/folders compact.

## 16. Implemented slice and deliberate simplifications

- New code stays flat: `api/app/db.py`, `api/app/ingestion.py`, one `SourcesPanel.tsx`, and focused integration tests. No module-directory scaffolding.
- Original bytes are immutable SQLite BLOBs alongside metadata, records and snapshots. This replaces a separate source-file directory and makes source/DB commit atomic.
- Parsing is bounded and synchronous inside a staging transaction. There is no worker service: interrupted staging rolls back, saved previews survive restart, and commit retries are idempotent. Persisted background jobs become necessary only when slower PDF/model work arrives.
- Dynamic synthetic/public workspaces, CSV/text preview, column mappings, explicit exclusions, exact integer money, controls, conflict detection, record revisions, scoped source viewing/download, immutable snapshots and source coverage are implemented.
- Stable CSV record IDs are required in this first implementation. School-only incomplete journals are preserved in staging with a blocker; a separate partial-ledger dataset mode is not implemented.
- Per-source options capture source system/version, logical document ID, applicable record/award, amount unit and source-stated control counts/totals. Known optional CSV fields use their canonical headers.
- Coverage indicates input availability; institutional completeness remains unverified. Full management statements and payroll allocation confirmation remain review-gated, even when the necessary source types exist.
- Evidence requests and committed-source responses persist task/source/snapshot links and a resumption event. The future agent runtime must independently review and consume that event; this change does not run or resume an LLM.
- Changed snapshots become stale, and evidence requests whose active source was replaced return to review. Report/calculation dependency invalidation awaits those unimplemented modules.
- Every workspace starts empty and only shows findings, approvals and reports derived from its own committed records.
- The first pack supports the ingestion acceptance scenario; 60/40-versus-80/20 agent reasoning, report recomputation, private benchmarking and memory remain later milestones.

Verification: backend tests (including accounting checks), TypeScript and production build, lint on changed frontend files, and a browser walkthrough of workspace creation, upload, commit and original-line viewing. See the tracker for the latest verification/handoff state.
