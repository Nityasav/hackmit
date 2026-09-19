# WORKPLAN — 16 hours, 4 people

Start **Sat Sep 19, 18:30**. Submit **Sun Sep 20, 10:30**. Four parallel tracks that only meet at the
contracts. If you are blocked for more than 15 minutes, say so in the channel and work around it.

## What already exists (do not rebuild)

| Built | Where |
| --- | --- |
| Dashboard: 8 tabs, workspace switcher, agent board + task drawer, expandable reasoning log, approvals with working approve/reject, report export | `web/` (Next.js 16, Tailwind v4, bun) |
| API skeleton: health, bundle, approval decision, demo stub, CORS | `api/app/main.py`, `api/app/store.py` |
| Exact-money engine: largest-remainder split, balance and cash-delta invariants, 27 passing tests | `api/app/accounting/money.py`, `api/tests/` |
| The data contract + two full fixtures (Sandbox University, MIT FY2025) | `contracts/` |
| Clickable design prototype | `docs/design/prototype.html` |
| Spec: product, accounting rules, agent prompts, evaluation, demo | `schooltrace/` |

The UI runs on `contracts/fixtures/*.json` with no backend, so **nobody is blocked on anybody**.

## Who owns what

| Track | Owner | Owns these paths | One-line goal |
| --- | --- | --- | --- |
| **UI** | hppddub | `web/` | Everything real on screen, and the demo controls |
| **Agent design** | Nitya | `api/app/agents/` | Five agents that actually investigate and explain themselves |
| **Workflows & data** | Stanley | `api/app/workflows/`, fixtures, demo script, evaluator scoring | The world the agents work in, and proof they did well |
| **Functionality** | Maxim | `api/app/accounting/`, `api/app/store.py`, `api/app/main.py`, DB | Numbers that are correct and survive an approval |

**Rules**
1. Work on `main` unless you're doing something risky; then branch `ui/*`, `agents/*`, `workflows/*`, `core/*`
   and merge back at a checkpoint. Pull before you push.
2. Stay inside your paths. Anything in `contracts/` is a **shared change**: announce it before pushing, and
   update `web/src/lib/types.ts` **and** `api/app/models.py` in the same commit.
3. Commit small and often. A broken `main` costs everyone.
4. After H8, nap in pairs. Keep one UI person and one backend person awake at all times.

## Timeline

| Time | Hour | Checkpoint | Must be true |
| --- | --- | --- | --- |
| 18:30 | H0 | Kickoff | Everyone has the repo running: `bun dev` and `uv run pytest` |
| 19:30 | H1 | **Contracts frozen** | Tool signatures agreed, fixture file names fixed, bundle fields final |
| 22:30 | H4 | **Vertical slice** | One real agent task on real fixtures → a finding with evidence → visible on the board |
| 02:30 | H8 | **Integration 1** | UI runs on the API (no fixtures). Live September run works. Approving recomputes |
| 06:30 | H12 | **Feature freeze** | October + memory + replay gate + evaluator numbers. No new features after this |
| 08:30 | H14 | **Rehearsed** | Replay run recorded, demo run twice end to end, README limitations honest |
| 10:30 | H16 | Submit | Tag, push, submit |

---

## Track 1 — UI (hppddub)

**Goal:** by H12 every number on screen comes from the API, and the demo drives from the UI.

| # | Task | By |
| --- | --- | --- |
| 1 | Run it, read `contracts/README.md`, open `docs/design/prototype.html`. Add `.env.local` with `NEXT_PUBLIC_API_URL` | H1 |
| 2 | **Demo control bar**: Reset · Inject issue · Add evidence (60/40 or 80/20) · Next month → `POST /api/demo/{action}`. Stub buttons first, they light up when Workflows lands | H4 |
| 3 | **Evidence viewer**: clicking an evidence node opens a side pane with the document page or CSV row, highlighted, plus its locator | H6 |
| 4 | **Live states**: loading, empty, failed, stale-snapshot banner, "API offline" fallback to fixtures without a crash | H8 |
| 5 | **MIT workspace**: source card, FY2024/FY2025 comparison, deep links to `#page=` in the PDF | H10 |
| 6 | **Board polish**: filter by agent and workflow, Esc closes the drawer, live step updates as the API pushes them | H10 |
| 7 | Export: close pack Markdown + evidence bundle JSON, print stylesheet | H12 |
| 8 | Projector pass at 1440×900: no horizontal scroll, readable from the back of a room | H14 |

**Done when:** with the API running, all 8 tabs render live data, the demo controls drive a real run, and every
evidence link opens its source.

## Track 2 — Agent design (Nitya)

**Goal:** by H8 a real model run produces findings, an auditor rejection, an evidence request and a decision
record for every action.

| # | Task | By |
| --- | --- | --- |
| 1 | Model adapter for `claude-sonnet-5` (tool calling + structured output) behind an interface, plus a **replay adapter** that reads a saved run. Token and cost counter feeds `run_budget` | H2 |
| 2 | **Tool gateway** (spec §8): `search_sources`, `read_source_span`, `query_financial_records`, `traverse_context`, `calculate`, `retrieve_precedents`, `submit_finding`, `propose_adjustment`, `request_evidence`, `submit_review`, `propose_playbook`, `prepare_payment_batch`. Signatures agreed with Maxim at H1 | H3 |
| 3 | Role prompts from `schooltrace/AGENT_PROMPTS.md`; enforce the response contract, including the `decision` block | H4 |
| 4 | **Orchestrator**: CFO plans → specialists run bounded (12 calls each) → Internal Auditor re-performs → human queue. Writes Task / TaskStep / Decision updates so the board animates | H6 |
| 5 | **Memory retrieval**: scope, dates, exclusions, contradictions. Emit `memory_checks` on every use. The stale PB-03 case must reject | H9 |
| 6 | Playbook proposal → hand to Maxim's replay gate → lands in Approvals | H11 |
| 7 | Record one good run to disk for replay mode, clearly labeled | H13 |

**Done when:** `POST /api/demo/inject_issue` on a configured key runs live agents end to end, and the same run
replays with no network.

**Guardrails:** agents never approve anything, never compute authoritative amounts themselves, and never see
the answer key.

## Track 3 — Workflows & data (Stanley)

**Goal:** by H4 the agents have a believable world; by H12 we can prove they did well.

| # | Task | By |
| --- | --- | --- |
| 1 | **Sandbox University September fixtures**: chart of accounts, opening trial balance, GL, payroll (including PAY-104 at $10,000 charged 100% to the award), invoices/POs/receipts (including the INV-2291 lookalike pair), award terms, budgets, enrollment | H3 |
| 2 | **Documents**: award GRANT-SS §4.2, the outdated budget sheet, SVC-REC-SEP service record, plus an 80/20 variant, transport contract A | H4 |
| 3 | **Hidden truth file** (expected findings, amounts, cleared lookalikes) stored outside anything the agents can read | H4 |
| 4 | **Workflow definitions**: the 5 pipelines, which stage spawns which task, which stages are human gates | H6 |
| 5 | **Scenario actions**: `reset`, `inject_issue`, `add_evidence(60/40 \| 80/20)`, `next_month` (October with contract B, which must defeat the old playbook) | H8 |
| 6 | **MIT source manifest**: page locators, verified facts, pledge rollforward components, extracted page text for the evidence viewer. Re-verify every citation against the PDF | H9 |
| 7 | **Evaluator scoring**: match findings to truth one-to-one, compute precision, recall, false positives, evidence-gap accuracy → `metrics.json` + `evaluation_report.md` | H12 |
| 8 | **Demo script + pitch** (2 min): the storyline, who speaks, the 3 money moments, and the fallback if the model is down | H13 |

**Done when:** the October run genuinely differs from September, the evaluator prints real scores with sample
sizes, and the demo script is on paper.

## Track 4 — Functionality (Maxim)

**Goal:** by H8 approving a correction recomputes real numbers from the ledger, with cash unchanged.

| # | Task | By |
| --- | --- | --- |
| 1 | **SQLite schema** + import with idempotency on `(source_system, source_record_id, source_version)`; load Stanley's fixtures; quarantine bad rows | H3 |
| 2 | **Accounting engine**: trial balance, opening + activity = closing, simplified statements, award schedule, allocation calculations. Extend `money.py`; keep every invariant under test | H5 |
| 3 | **Bundle builder**: replace the fixture seed in `store.py` so tasks, findings and report numbers come from the DB and the agents' writes | H7 |
| 4 | **Approvals**: version check, distinct human approver, idempotent apply, recompute dependents, new snapshot, mark stale outputs | H8 |
| 5 | **Playbook store + replay gate**: re-run a prior month with the candidate playbook and count new false positives against the truth file. Blocks activation on failure | H11 |
| 6 | **Run budget + telemetry**: tool calls, tokens, cost, latency per agent, surfaced in the bundle | H12 |
| 7 | **Tests**: reimport doesn't double count, unbalanced journal rejected, reclass leaves cash unchanged, applying an approval twice is a no-op, stale proposal rejected | H12 |

**Done when:** every number in the UI traces to a calculation in the engine, and `uv run pytest` is green.

---

## Cut list (in this order, no debate)

1. OCR and PDF parsing — documents are Markdown/CSV with locators
2. Bank reconciliation, AR aging, 13-week cash forecast
3. Full graph visualization — the evidence path in Findings is enough
4. More than one paired memory ablation run (n=1, and say so)
5. Postgres, auth, multi-tenancy, PDF export
6. Any new tab

**Never cut:** exact integer-cent math, evidence on every claim, the auditor rejection, human approval,
the stale-playbook rejection, and honest labels on recorded vs live.

## Fallback

If the model API dies during the demo: switch to the recorded run (Nitya, task 7). It is labeled
**Recorded run** in the UI, and calculations, approvals and recomputation still run live. Never present a
recorded run as live.

## The demo we are building toward

MIT workspace: clean opinions, no findings, pledge rollforward ties → switch to Sandbox → watch the agents
work on the board → open a card, see its steps and why → the Auditor refuses an unsupported claim → add the
service record → approve the $4,000 reclassification, cash unchanged, every report updates → Reasoning log:
why it chose that → next month: the learned playbook applies, the stale one is rejected → Learning: memory on
vs off, measured.
