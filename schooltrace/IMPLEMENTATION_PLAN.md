# Build process and resource plan

## 1. Resources

| Resource | Minimum | Purpose |
| --- | --- | --- |
| Team | 2–4 builders; one person owns integration | Data/accounting, agent backend, UI, evaluation/demo |
| Domain review | A finance/accounting reviewer if available | Check assumptions and final accounting examples |
| Model access | One model with tool calling and structured output | Run distinct reasoning roles; provider adapter avoids lock-in |
| Runtime | Python API/worker and TypeScript frontend | Typed calculations and interactive investigation UI |
| Storage | PostgreSQL and local source directory | Exact financial records, graph tables, checkpoints |
| Parsing | CSV plus text-based documents initially | Preserve locators without early OCR complexity |
| Evaluation | Private fixture generator and deterministic scorer | Hidden issues and memory ablation |
| Deployment | Local demo first | Avoid live financial connectors and sensitive records |

Suggested team planning allowance: 24–36 hours and a configurable $25–$100 model-spend ceiling. This is an internal budget choice, not a provider price estimate or a guarantee of sufficiency. Measure actual usage and stop at the configured cap. Reserve several hours for integration and rehearsal.

No paid graph service, fine-tuning, live banking, real payroll, or production institution data is needed. Use SQL node/edge tables before adding graph infrastructure. Pin dependencies after checking official documentation and compatibility during implementation.

## 2. Proposed application repository

```text
schooltrace-app/
  README.md
  .env.example
  apps/web/                    # overview, investigation, graph, reviews, reports
  services/api/                # authorization, imports, runs, reviews, exports
  services/worker/             # orchestrator and resumable agent tasks
  packages/contracts/         # JSON schemas / generated client types
  packages/accounting/        # exact calculations and invariant checks
  packages/context/           # graph projection, temporal queries, memory filters
  packages/agents/            # role prompts, model adapter, tool gateway
  migrations/
  fixtures/public/            # runtime-safe developer inputs
  tests/                      # unit, integration, agent-behavior cases
  scripts/                    # seed, reset, run, export
  docs/                       # this specification package
```

Keep evaluator-private fixtures outside the runtime-mounted repository subtree or in a separately permissioned evaluator project. Runtime manifests list exactly which source directories are accessible. `.env.example` contains placeholders only.

## 3. Milestones and gates

### M0 — Lock scope and executable contracts (hours 0–2)

- Confirm demo accounting profile and institution; choose one supported model/provider.
- Define canonical record IDs, monetary representation, snapshots, finding schema, and review permissions.
- Build a minimal seed: one payroll allocation issue, one legitimate lookalike, one grant agreement, balanced opening and current entries.
- Gate: schema-validated seed and independently calculated expected balances.

### M1 — Deterministic financial spine (hours 2–7)

- Import/hash sources, preserve locators, normalize records, enforce idempotency.
- Implement ledger balance, trial balance, management statements, and allocation calculations.
- Implement baseline versus approved scenario, immutable proposals, and review/application endpoint.
- Gate: invalid journals rejected; valid example ties; reimport and reapplication have no duplicate effect.

### M2 — Evidence graph and first investigation (hours 7–12)

- Add typed facts, source spans, graph edges, policy applicability, and source viewer.
- Add lead and one specialist using real tools and structured findings.
- Add independent auditor and human evidence queue.
- Gate: user can follow a real finding from question to source to calculation to reviewed correction.

### M3 — Full agent team and downstream outputs (hours 12–19)

- Add transaction, payroll/budget, and restricted-funds specialist coverage.
- Add bank/AP/AR/grant schedules, budget comparison, and bounded cash forecast.
- Implement dependency invalidation and report snapshots.
- Gate: reviewer challenge triggers a new evidence-driven step; approved reclassification updates correct outputs without moving cash.

### M4 — Reviewed memory and month two (hours 19–24)

- Implement precedent review, temporal scope, exclusions, supersession, and retrieval logging.
- Add recurring valid use and changed-contract invalidation cases.
- Gate: month-two actions visibly differ with memory; invalid memory is rejected.

### M5 — Evaluation and demo polish (hours 24–32)

- Expand synthetic fixture families; isolate hidden truth from runtime tools.
- Run paired memory experiments and score claim support and financial consistency.
- Add report export, incomplete-state UI, runtime/cost telemetry, and replay labeling.
- Gate: all acceptance criteria have evidence or are honestly marked incomplete.

### M6 — Rehearsal and contingency (remaining time)

- Rehearse reset -> live run -> evidence injection -> approved correction -> report.
- Save one successful run for clearly labeled replay if a model/network outage occurs.
- Record known failures, sample sizes, and scope limits in the final README.

For a 24-hour event, reduce dataset size and UI polish first. Keep ledger correctness, original evidence, auditor challenge, reviewed memory, and the paired comparison. Advanced facilities accounting, graph animations, OCR, and production integrations are first to cut.

## 4. API contract sketch

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
| Agent | Missing evidence, counterevidence, reviewer rejection, changed policy, bounded stop |
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
