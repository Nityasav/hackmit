# Contracts

## Intake contract v2

The existing bundle remains compatible with `sandbox` and `mit`. New persisted workspace IDs are
`ws-` plus 16 hexadecimal characters; they are validated by lookup, never treated as filesystem paths.
Bundles add `contract_version: 2`, optional workspace `intake`, `currency`, `profile`, and execution mode
`not_started`. New workspaces contain no demo findings/tasks. The TypeScript types in `web/src/lib/types.ts`
describe intake responses; request models and validation live in the flat `api/app/ingestion.py` module.

| Method/path | Payload / result |
| --- | --- |
| GET /api/workspaces | Persisted workspace configurations; fixed demos remain separate |
| POST /api/workspaces | Name, synthetic/public kind, entity type, jurisdiction, currency, start/end, scope |
| POST /api/workspaces/{ws}/imports | Multipart `files` plus JSON `metadata` array (one FileOptions per file) → persisted preview |
| GET /api/workspaces/{ws}/imports | Recent saved imports |
| GET /api/workspaces/{ws}/imports/{id} | Status, preview version, base revision, per-file fields/rows, controls and issues |
| PATCH /api/workspaces/{ws}/imports/{id}/mapping | `expected_version`, `files: {source_id: FileOptions}` → new validated preview |
| POST /api/workspaces/{ws}/imports/{id}/commit | `expected_version`, `idempotency_key` → committed snapshot; 409 on stale/invalid state |
| GET /api/workspaces/{ws}/coverage | Per-capability source availability, counts, source list, evidence requests |
| GET /api/workspaces/{ws}/sources/{id} | Metadata plus numbered original text lines (`start`, `limit` ≤ 200) |
| GET /api/workspaces/{ws}/sources/{id}/spans/{line} | One original line, hash and source version |
| GET /api/workspaces/{ws}/sources/{id}/download | Unchanged bytes as an attachment |
| POST /api/workspaces/{ws}/evidence-requests | `title`, requested `role`, optional `task_id` |
| POST /api/workspaces/{ws}/evidence-requests/{id}/responses | `source_id`, `expected_version`; requires matching-role committed active evidence |

FileOptions: `role`, `source_system`, positive integer `source_version`, optional `external_id` (stable
document identity), `applies_to`, `mapping` (canonical field → CSV header), `amount_unit` (major/minor),
optional `expected_rows`/`expected_debit`/`expected_credit`, `excluded` and required `exclusion_reason`
when excluded. Client mappings are revalidated server-side. All references are workspace-scoped.

Preview statuses: `needs_mapping`, `needs_review`, `ready_to_commit`, `committed`. Parsing happens inside
the staging transaction; interrupted operations roll back. Any validation issue blocks commit. Explicit
exclusions remain in the saved batch but never become active evidence/records. Only the first 500 issues
and first 100 revision diffs are returned; counts report the full population.

Source identity uses `(workspace, role, source_system, stable_record_id, source_version)`; row order and
filenames do not define financial identity. Same-key changed payloads conflict, later versions supersede
without deleting history, and duplicate-only imports keep the existing snapshot. Every normalized record
stores its original source ID and line locator. Source types do not automatically create ledger postings.

Coverage states are source readiness only; full management statements and allocation confirmation stay
`needs_review` even when inputs exist. `coverage_verified` remains false until a real completeness review
exists. Evidence `supplied` is not `verified`; attachment saves a future-runtime resumption event, and a
superseding source returns the request to `needs_review`.

The small public synthetic fixture pack is `fixtures/intake.json`; it is developer input, not a hidden
benchmark or a saved agent run. Existing UI fixtures remain unchanged for teammate compatibility.

The seam between the four workstreams. **Change these three together:**

| File | Owner of the change |
| --- | --- |
| `contracts/fixtures/*.json` | whoever adds the data |
| `web/src/lib/types.ts` | UI |
| `api/app/models.py` | Functionality |

If you change a field, say so in the team channel before you push. Everything else can move independently.

## The bundle

The dashboard renders **one JSON payload per workspace**: `GET /api/workspaces/{sandbox|mit}/bundle`.
With no API running, the web app reads `contracts/fixtures/{ws}.json` directly, so the UI works offline.

```
Bundle
├─ workspace      id, name, kind (synthetic|public), period, mode (live|recorded|scripted),
│                 snapshot_id, disabled_tabs[], model, run_budget
├─ agents[]       cfo | ap | py | gr | au — name, role, status, "doing" (drives the live strip)
├─ briefing       CFO Agent text (**bold** marks highlights) + action buttons
├─ kpis[]         label, value, note, tone
├─ workflows[]    id, name, owner, progress, stages[] (done|running|human|todo)
├─ tasks[]        Agent board cards: column (queued|working|needs_you|auditor_review|done),
│                 progress, eta_s, tool_calls, steps[], todos[], rationale, approval_id
├─ findings[]     status, amount_cents, verified_by, evidence[] (the graph path)
├─ approvals[]    kind (journal|payment|playbook|evidence), journal[], effects[], status
├─ decisions[]    Reasoning log: when / how (tool calls) / why / alternatives / memory_checks / outcome
├─ playbooks[]    RSI: replay gate result, uses, status (active|needs_approval|retired|blocked)
├─ ablation       memory on vs off. `example: true` until the evaluator produces real numbers
└─ report         sections, before/after comparisons, applies_approval
```

## Rules

1. **Money is integer cents.** `amount_cents: 400000` is $4,000.00. The UI formats it; nothing else does.
2. **Task columns map to spec statuses**: `queued → queued`, `running → working`, `needs_evidence → needs_you`,
   `submitted → auditor_review`, `review_accepted → done`.
3. **Every finding carries evidence**, and every amount traces to a calculation ID. No bare numbers.
4. **`decisions[]` holds concise decision records**, never raw chain-of-thought (spec.md §8).
5. **`example: true` on ablation** means the numbers are placeholders. Remove it only when the evaluator
   wrote them (DATA_AND_EVALUATION.md §9).
6. **Only a human decides an approval.** Agents propose; `POST /api/approvals/{id}/decision` is the human path.

## Endpoints (hackathon minimum)

| Endpoint | Behavior |
| --- | --- |
| `GET /api/health` | liveness |
| `GET /api/workspaces/{ws}/bundle` | everything the dashboard renders. The web app polls every 2s |
| `POST /api/approvals/{id}/decision` | `{workspace, decision}` → updated bundle |
| `POST /api/demo/{action}` | `reset`, `inject_issue`, `add_evidence`, `next_month` |
