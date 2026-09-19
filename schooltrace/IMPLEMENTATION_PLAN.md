# Build process and resource plan

## 1. Resources

| Resource | Minimum | Purpose |
| --- | --- | --- |
| Team | 4 builders: UI, Agent design, Workflows, Functionality (see `/WORKPLAN.md`); one person owns integration at each checkpoint | Parallel work on directory-owned areas joined by `contracts/` |
| Domain review | A finance/accounting reviewer if available | Check assumptions and final accounting examples |
| Model access | Claude Sonnet 5 (`claude-sonnet-5`) with tool calling and structured output, plus a labeled replay adapter | Run distinct reasoning roles; provider adapter avoids lock-in |
| Runtime | FastAPI (Python, uv) API/worker and Next.js 16 + Tailwind v4 frontend (bun) | Typed calculations and interactive investigation UI |
| Storage | SQLite for the hackathon (Postgres-portable schema) and a local source directory | Exact financial records, graph tables, checkpoints, decision records |
| Parsing | CSV plus text-based documents initially | Preserve locators without early OCR complexity |
| Evaluation | Private fixture generator and deterministic scorer | Hidden issues and memory ablation |
| Deployment | Local demo first | Avoid live financial connectors and sensitive records |

The actual time left is **about 16 hours** (Sat Sep 19 ~6pm → Sun Sep 20 ~10am, 2026). The original suggestion was 24–36 hours; §3 is the compressed plan. Keep a configurable $25–$100 model-spend ceiling. This is an internal budget choice, not a provider price estimate or a guarantee of sufficiency. Measure actual usage and stop at the configured cap. Reserve several hours for integration and rehearsal.

No paid graph service, fine-tuning, live banking, real payroll, or production institution data is needed. Use SQL node/edge tables before adding graph infrastructure. Pin dependencies after checking official documentation and compatibility during implementation.

## 2. Application repository (hackathon layout)

```text
hackmit/
  README.md                   # how to run web + api, demo steps, known gaps
  WORKPLAN.md                 # 4-person split, checkpoints, interfaces
  web/                        # Next.js 16 App Router, TS, Tailwind v4, bun
                              #   8 tabs + workspace switcher; reads one JSON bundle per workspace
                              #   from contracts/fixtures when NEXT_PUBLIC_API_URL is unset, else polls the API
  api/                        # FastAPI (Python, uv)
    app/main.py               #   GET /api/health, GET /api/workspaces/{ws}/bundle,
                              #   POST /api/approvals/{id}/decision, POST /api/demo/{action}
    app/accounting/           #   integer-cent calculations, invariants L01–L13, scenario apply
    app/agents/               #   model adapter (+ replay), tool gateway, role prompts, orchestrator, decision records
    app/workflows/            #   workflow/stage definitions, demo scenarios, payment batch + payroll flows
  contracts/                  # README.md (bundle schema) + fixtures/sandbox.json, fixtures/mit.json
  docs/design/prototype.html  # approved UI prototype (style C)
  schooltrace/                # this specification package
```

The earlier multi-package layout (`apps/`, `services/`, `packages/`) is a fine target after the hackathon. `contracts/` is the only shared seam, so announce schema changes to the team before merging. Keep evaluator-private fixtures outside the runtime-mounted repository subtree or in a separately permissioned evaluator project. Runtime manifests list exactly which source directories are accessible. `.env.example` contains placeholders only.

## 3. Compressed 16-hour plan (4 people)

The owner-level task lists are in `/WORKPLAN.md`. The checkpoints below are shared gates: everyone merges to `main` and the whole team runs the demo path. H0 ≈ 6pm Saturday.

| Checkpoint | By | Gate (everyone verifies) |
| --- | --- | --- |
| H0 → H1 | ~7pm | Contracts frozen for v1: bundle schema, task/decision/playbook records, tool signatures, workflow IDs. Web runs on fixtures; API `/api/health` and `/bundle` (fixture pass-through) run |
| H4 | ~10pm | **Vertical slice.** Seed ledger (payroll allocation issue, invoice lookalike, award terms) balances. `calculate(alloc_split)` returns the exact $4,000. One agent (Payroll & Budget) runs a real task via the tool gateway and emits a decision record. Web renders it from the API |
| H8 | ~2am | **Integration.** CFO Agent → 3 specialists → Internal Auditor rejects CL-7 → evidence request → human attaches service record → reclass proposal → Approvals applies it (cash unchanged). Workflows and Agent board are driven by real task state. MIT workspace data is live |
| H12 | ~6am | **Feature freeze.** Month two: PB-05 applied, PB-03 rejected as stale, PB-07 through the replay gate. One paired memory on/off run saved. Reports before/after. Only bug fixes after this point |
| H14 | ~8am | **Recorded run + rehearsal.** Save one successful live run as the labeled replay. Two full rehearsals of the DEMO.md route (4–6 min). README lists what is live, recorded, or scripted |
| H16 | ~10am | **Submit.** Devpost, video if required, repo tagged |

If the H8 gate slips, drop to one specialist plus the auditor for live runs. Show the rest from a labeled recorded run. Do not fake live output.

### Cut list (decided now, not at 4am)

- **Cut:** OCR and PDF extraction (use Markdown/text source documents with line locators), bank reconciliation, AR aging, the 13-week cash forecast, facilities/capital cases, full graph visualization (show the evidence path inside Findings instead), multi-tenant auth (single local reviewer identity), and SSE (poll the bundle endpoint).
- **Reduce:** one paired memory ablation run instead of three repetitions (reported as demonstration evidence, n=1). A small fixture set: one district-sized sandbox, two months, and the planted cases the demo route needs plus benign lookalikes.
- **Keep, never cut:** exact integer-cent math and invariants, original evidence locators, the auditor challenge, human approval gates, the stale-playbook rejection, decision records behind every Reasoning log entry, and honest live/recorded/scripted labels.

## 4. API contract sketch

Hackathon minimum (implement these first; the rest are targets):

| Endpoint | Behavior |
| --- | --- |
| GET /api/health | Liveness plus model/replay mode |
| GET /api/workspaces/{ws}/bundle | One JSON bundle per workspace (`mit`, `sandbox`): briefing, agents, tasks, workflows, findings, approvals, report, decisions, playbooks. The schema is in `contracts/README.md` |
| POST /api/approvals/{id}/decision | Human approve/reject with proposal version and rationale; applies idempotently |
| POST /api/demo/{action} | Demo controls: `reset`, `inject_issue`, `add_evidence`, `next_month`, `run` |

Full target:

| Endpoint | Behavior |
| --- | --- |
| POST /imports | Validate type/size, hash and stage sources, return batch ID |
| GET /imports/{id}/coverage | Coverage totals, quarantine rows, unresolved mappings |
| POST /investigations | Start bounded job with institution, period, snapshot, question |
| GET /investigations/{id}/events | Stream persisted events and status |
| GET /findings/{id} | Structured finding, evidence, counterevidence, review |
| GET /sources/{id}/spans/{span} | Authorized original evidence and locator |
| GET /context | Bounded temporal subgraph scoped to institution and snapshot |
| POST /evidence-responses | Attach human-supplied source to a pending request |
| POST /adjustments/{id}/review | Human decision with proposal version and rationale |
| POST /scenarios/{id}/apply | Idempotently apply approved proposal; trigger recomputation |
| POST /precedents/{id}/review | Activate/reject scoped procedural memory |
| GET /reports/{id} | Immutable report snapshot and staleness state |
| GET /exports/{id} | Evidence/report bundle scoped to user authorization |

Use request validation, authenticated reviewer identity, idempotency keys for mutations, and expected-version checks. Return machine-readable reasons for stale proposals, missing evidence, unsupported basis, and run-budget exhaustion. The endpoint path alone never supplies authorization.

## 5. Test matrix

| Layer | Required tests |
| --- | --- |
| Arithmetic | Journal balancing, rounding, reversals, payroll gross/net, fee-net receipts |
| Import | Reimport, revised source, partial failure, unknown account, duplicate economic event |
| Ledger | Baseline preserved, scenario application once, statement tie-out, opening carry-forward |
| Graph | Temporal scope, supersession, tenant filtering, SQL revision mismatch, transitive invalidation |
| Agent | Missing evidence, counterevidence, reviewer rejection, changed policy, bounded stop, decision record tool calls match logged events |
| Learning | Replay gate blocks a playbook that adds a false positive; stale playbook retired on superseded contract; agents cannot activate playbooks |
| Payments | Batch release requires a distinct human; vendor-bank-change items held; release is simulated only |
| Authorization | Agent cannot approve, reviewer cannot apply stale version, private labels unreachable |
| Reports | Narrative amount matches calculation, stale snapshot labeled, overlapping effects not summed |
| Evaluation | Exact metric denominators, duplicate finding collapse, hidden-label isolation, matched ablation state |

Do not test by asserting that the model uses a particular wording. Test financial outputs, tool traces, state transitions, source validity, and disposition.

## 6. Performance and observability

Development targets: seed/import under 30 seconds for the small demo; interactive evidence opening under one second locally; full live investigation within three minutes where provider latency permits. Treat these as targets to measure, not promises.

Expose per-agent status, requests, failures, tool counts, latency, tokens, cost, snapshot IDs, and applied-memory IDs. Cache extraction by source hash, calculations by input/version hash, and retrieval by snapshot/scope. Do not cache a finding across changed evidence without revalidation.

## 7. Risks and design responses

| Risk | Response |
| --- | --- |
| Five agents repeat the same speculation | Distinct tasks/tools, structured handoffs, source re-performance |
| Context graph becomes decoration | Require retrieval, applicability checks, and invalidation to use graph edges |
| UI looks like a static dashboard | Agent board, live status strip, decision records in the Reasoning log, ✦ AI labels (spec §11) |
| 16h is not enough | Cut list in §3; recorded run saved at H14; checkpoints enforced |
| Memory copies a prior mistake | Human-reviewed activation, source dates, exclusions, negative-transfer tests |
| Beautiful reports conceal bad math | Deterministic financial spine before narrative generation |
| Hidden tests leak into runtime | Separate grader storage/permissions and auditable retrieval boundary |
| Too much scope | One district/profile, two months, narrow deep cases, explicit extension list |
| All cases are suspicious | Add legitimate lookalikes and score false positives |
| Framework APIs differ from assumptions | Verify official docs at build time; isolate model/framework adapter |
| LLM unavailable during demo | Clearly labeled replay of a real saved run, never presented as live |
| Domain overclaim | Management-only report labels, policy-source versions, specialist review before deployment |

## 8. Definition of done

A fresh checkout can install, seed, run, and export a complete demo with documented commands; a configured provider runs real agents; replay mode is explicitly labeled; tests pass; private truth is inaccessible; reports link to evidence; corrected outputs tie; and the saved month-two comparison reports actual measured results and limitations.
