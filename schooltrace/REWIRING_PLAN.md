# Rewiring plan — remove fake data, connect the tabs

Branch: `refactor/real-data-wiring`
Written: 2026-09-19
Goal: every number, task, finding, approval and report on screen traces to committed records, a
real agent run, or a deterministic calculation. Nothing that is isolated or decorative survives.

---

## 0. Do not touch

**The Learning tab is owned by someone else right now.** This plan does not modify, and no task in
it may modify:

- `web/src/app/learning/page.tsx`
- `web/src/components/ui/features-card.tsx`
- `Playbook`, `Replay`, `Ablation`, `AblationRow` in `api/app/models.py` and `web/src/lib/types.ts`
- the `playbooks` / `ablation` keys of the bundle contract

Phase 2 must keep emitting `playbooks` and `ablation` in the bundle exactly as it does today
(`[]` and `null` for intake workspaces) so their work drops in without a merge conflict.
`disabled_tabs` keeps `"learning"` until they say otherwise.

---

## 1. What is actually fake — the verified inventory

Established by reading the code, not the README. Line refs are on `main` at `e79a087`.

| # | Thing | Evidence | Verdict |
|---|---|---|---|
| F1 | Agent board is a stock vendor template | `web/src/app/board/page.tsx:108` hardcodes "Add authentication", "John Doe", `Jan 10, 2025`; never calls `useData()` | Replace |
| F2 | `TaskDrawer.tsx` orphaned | zero imports repo-wide | Reuse in F1 |
| F3 | Intake bundle hardcodes empty collections | `api/app/ingestion.py:703` — `kpis: []`, `workflows: []`, `approvals: []`, `report: {...no report}` | Derive |
| F4 | `disabled_tabs` is a constant | `api/app/ingestion.py:696`, `web/src/lib/data.tsx:28` | Derive from state |
| F5 | Coordinator results never reach the dashboard | `cfo_runs` lives in a separate SQLite file (`api/app/cfo/api.py:88`); nothing joins it to `ingestion.bundle()` | Unify |
| F6 | `/cfo` is an isolated page | only reachable by a link; its output is invisible to every tab | Fold in |
| F7 | Approvals need recomputation | Human decisions must update the derived projection coherently | Build |
| F8 | Reports need a derived baseline | Comparisons must come from saved calculations | Derive |
| F9 | Workspace state must be live | Every workspace is derived from persisted records and runs | Build |
| F10 | `run_loop.py` stack is unreachable over HTTP | 561 lines + `ap_tools`/`ap_write_tools`/`au_write_tools`/`cfo_tools`/`decision_tools`; only `api/scripts/*.py` and tests call it | Repoint, don't delete |
| F11 | `ap_tools` reads its own JSON fixture | `api/app/agents/data/ap_sandbox.json` (7.7 KB) instead of committed records | Repoint |
| F12 | `POST /api/demo/{action}` half-implemented | `api/app/main.py:95` — `inject_issue`, `add_evidence`, `next_month` return 501 | Implement or remove |
| F13 | Ledger invariants oversold | README claims L01–L13; only L01, L02, L07, L11 exist in `accounting/money.py`, `accounting/payroll.py` | Correct the docs |
| F14 | AP and grants have no calculator | `accounting/` contains only `money.py` + `payroll.py`, so AP/GR claims can never carry an amount | Build minimum |

### The two disconnected agent stacks

This is the root cause of most of the above, and Phase 1 exists to fix it.

- **Stack A — snapshot triage.** `POST /api/workspaces/{ws}/agent-runs` → `agents/cfo.py`. Agents:
  `cfo`, `grants_compliance`, `internal_auditor` only (`agents/cfo.py:73`). Writes to `agent_runs`
  in the intake DB. **Reaches the dashboard.**
- **Stack B — five-agent coordinator.** `POST /api/cfo/runs` → `cfo/engine.py`. Full CFO → ap/py/gr
  → auditor loop, live adapters registered in `integrations/cfo_factory.py:13`. Writes to a
  **separate** SQLite file. **Reaches nothing but `/cfo`.**
- **Stack C — `run_loop.py`.** A third implementation, with the only working
  `submit_finding` / `request_evidence` / `prepare_payment_batch` write tools in the repo
  (`agents/ap_write_tools.py:31,67,91`), bolted to `store.py`'s in-memory fixture bundles.
  **Reaches nothing.**

`store.py` already exposes exactly the write API the dashboard needs — `append_finding`,
`append_approval`, `apply_review`, `append_decision`, `create_task`, `update_task`,
`set_briefing`. Its only defect is that it is an in-memory dict seeded from JSON. That is the seam.

---

## 2. Target architecture

```
committed records (SQLite)
        │
        ├──► deterministic calculations (accounting/)
        │
        ▼
   ONE run store (agent_runs + cfo_runs, same DB, same transaction)
        │
        ▼
   projection.py ── the single place a Bundle is built
        │
        ├── kpis          ← coverage + accepted claims + calculations
        ├── tasks         ← real TaskState from whichever stack ran
        ├── findings      ← accepted claims + auditor verdicts
        ├── approvals     ← proposals written by agents, decided by humans
        ├── workflows     ← derived from run/task status
        ├── report        ← accepted claims + before/after recompute
        └── decisions     ← run events
        │
        ▼
   every tab
```

One rule to enforce in review: **`projection.py` is the only module that may construct a
`Bundle`.** If a page needs something, it gets added to the projection, never hardcoded in the
component.

---

## Phase 1 — Unify the run stores *(keystone; everything else depends on it)* — **DONE**

Steps 1 and 2 landed. Steps 3 and 4 were misplaced in this plan and moved:

- **Step 3 (back `store.py` with SQLite) moved to Phase 4.** Phase 2 makes findings, tasks and
  decisions *derived* from runs rather than stored, so tables for them would have been built and
  immediately orphaned. The one collection that genuinely cannot be derived from a run is
  **approvals**, because a human decision is not in the run — so that table is designed once, in
  Phase 4. The likely outcome is that `store.py` shrinks rather than gains a backend.
- **Step 4 (remove the `main.py` branch) moved into Phase 2**, where the projection exists to
  absorb it.


1. Move `cfo_runs` into `api/app/db.py`'s `SCHEMA`. Bump `PRAGMA user_version` to 3 and raise the
   guard in `db.connect()` accordingly.
2. Rewrite `api/app/cfo/repository.py` to use `db.connect()` instead of its own
   `sqlite3.connect(self.path)`. Drop `CFO_DB_PATH` and the `.venv/cfo-runs.sqlite3` default in
   `api/app/cfo/api.py:88`.
3. Route all dashboard bundles through the SQLite-backed projection layer.
4. Remove any alternate fixture-backed bundle path.

**Done when:** no workspace-ID special case remains, and a coordinator run and a triage run on the
same workspace are readable in one transaction.

**Risk:** this touches the DB schema. Write the migration as additive-only (`CREATE TABLE IF NOT
EXISTS`), and add a test that opens a `user_version = 2` database and reads it without loss.

---

## Phase 2 — One projection layer — **DONE**

Landed as `api/app/projection.py`. `projection.bundle(ws)` is the single entry point and the only
module that builds a `Bundle`; a test enforces that. `main.py`'s sandbox/MIT branch is gone, absorbed
into the documented `RECORDED` seam that Phase 8 closes.

Beyond the steps below, two things came out of the work:

- **Evidence previews.** The plan only asked for a locator, but the UI's "open source" control then
  opened onto an empty box — a dead end of exactly the kind this branch exists to remove. Cited
  originals are now read once per bundle, deduplicated, and their first lines carried on the node.
- **Failed and blocked tasks are decisions too.** The first pass only logged `task.finished`, which
  made an abandoned task look like it had never run.

Verified end to end: a five-agent engine run over a committed snapshot produces three
auditor-verified findings on the Findings tab, with sha256-stamped locators and real excerpts, three
tasks on the board with real tool-call counts, and eight decisions across all five agents.


1. New `api/app/projection.py`. Move `_agent_projection` (`ingestion.py:611`) and `bundle`
   (`ingestion.py:650`) into it and delete them from `ingestion.py`.
2. Teach it to read **both** run kinds and merge them: triage findings, and coordinator
   `AcceptedClaim`s (`cfo/schemas.py` `AcceptedClaim`) which already carry `claim`, `review` and an
   optional `Calculation`.
3. Map `AcceptedClaim` → `Finding`:
   - `claim.title` → `title`; `claim.conclusion` → `summary`
   - `claim.disposition` (`substantiated`/`cleared`/`explained`) → `Finding.status`
   - `calculation.amount_cents` → `amount_cents` — **only** when a `Calculation` exists, otherwise
     `None` with the existing `amount_note`. Never let a model-authored number through.
   - `review.verdict == "accept"` → `verified_by = "au"`
   - each `evidence_id` → an `EvidenceNode` with a real `locator`, resolved through
     `ingestion.source_view` so the Findings evidence trail links to the actual line
4. Keep emitting `playbooks: []` and `ablation: None` unchanged (see §0).

**Done when:** a five-agent run's accepted claims appear in the Findings tab with working evidence
links, and `ingestion.py` no longer constructs a bundle.

---

## Phase 3 — Real KPIs, real Reports — **DONE**

Step 4 needed no work: `AdvancedStats` already returns `null` when no finding carries an amount, so
there was no demo fallback to remove. Two things were needed that the plan missed:

- **`Report.markdown` was added to the contract** (Pydantic, TypeScript and `contracts/README.md`
  together, per the contract rule). Without it the Reports tab had no way to *reuse*
  `cfo/reporting.py` — it was rendering its own Markdown client-side, a second renderer of the same
  document. The export is now the run's published report verbatim, with the client-side renderer
  left only as the fallback for the recorded fixtures until Phase 8.
- **The Command center short-circuited intake workspaces** straight to `SourcesPanel`, so the KPIs
  this phase built would have been invisible there. It now shows the briefing and the KPI strip
  above the sources once a run has produced them.

The Reports tab no longer decides what to show based on *which workspace* it is, but on whether the
work happened: a published report or any findings.


1. **KPIs** (`kpis: []` today). Derive five, each from a source that already exists:
   - records committed / sources active — `ingestion.coverage`
   - open evidence gaps — `evidence_requests` where `status='open'`
   - findings by status — projection
   - total exposure in cents — sum of `Calculation.amount_cents` over accepted claims only
   - run budget consumed — `run.tool_calls` / `run.model_calls`

   Any KPI with no backing data is **omitted**, not shown as zero.
2. **Reports.** Replace the hardcoded `"No investigation report yet"` (`ingestion.py:704`) with a
   report built from accepted claims. `cfo/reporting.py:render()` already produces exactly this
   Markdown from `run.accepted` — reuse it rather than writing a second renderer.
3. **Before/after comparisons.** Only meaningful once approvals recompute something, so this
   lands with Phase 4. Until then the projection emits `comparisons: []` and the UI renders the
   empty state rather than fixture rows.
4. Remove `AdvancedStats`' fallbacks if any silently substitute demo numbers when `findings` is
   empty — verify `web/src/components/ui/advanced-stats.tsx` end to end and make it render an
   empty state instead.

**Done when:** Reports shows a real exported document for an intake workspace, and every KPI tile
can be traced to a query.

---

## Phase 4 — Approvals end to end — **DONE (with one limit stated)**

Landed as `api/app/approvals.py` plus an `approvals` table (schema 3 → 4, and `db.SCHEMA_VERSION` is
now a single constant so the migration test stops needing an edit per bump).

**The limit worth knowing.** Step 2 asked for a journal from any claim whose `proposed_action`
implies a ledger change. A `proposed_action` is model-authored prose, and prose is not a journal, so
nothing is derived from it. A journal is built only from a deterministic calculation whose category
is `reclassification`, **and only when the committed records name both funds.** The sample pack
names an award but no destination fund, so on that data the correct output is not a journal — it is
a request for the structured allocation record that `accounting/payroll.py` says is required.
Inventing a destination fund is precisely what the fixture's `ADJ-12` did, and what the accounting
module's own docstring forbids. The journal path is built, balance-checked and tested; it produces
a journal the moment records carry funds.

Departures from the plan, all forced by something real:

- **A fifth approval kind, `decision`.** A substantiated claim with no calculation is neither a
  journal nor an evidence request, and labelling it `evidence` made the UI button read "Mark
  provided" for a proposal that asks for nothing.
- **`Approval.finding_id` added to the contract**, so an approval links to the finding it resolves
  and the before/after can tell which exposure a decision clears.
- **`disabled_tabs` is now derived**, not a constant: a public-documents workspace holds no
  transactions, so Approvals stays off there. An existing ingestion test caught this.
- **The reviewer guard was extended to `/api/approvals`**, which became a write path into intake
  data the moment decisions stopped being demo-only.

Deferred: repointing Stack C's `ap_write_tools` at the new table. Those tools are unreachable over
HTTP and their tests pin `store.py` behaviour; Phase 9 decides that stack's fate.


The pitch is "agents propose, humans decide." Today nothing proposes and deciding does nothing.

1. New `approvals` table in `db.py`: `id, ws, snapshot_id, run_id, agent, kind, title, summary,
   journal, effects, verified, status, decided_at, decided_by`.
2. **Proposals.** `ap_write_tools.submit_finding` / `request_evidence` / `prepare_payment_batch`
   already build correctly shaped approval records with journal lines — repoint them at the new
   table (Phase 1 makes this a no-op at the call site). Add the same capability to the coordinator:
   an `AcceptedClaim` whose `proposed_action` implies a ledger change becomes a `journal` approval.
3. **Journal validity.** Every proposed journal runs through
   `accounting/money.py:assert_balanced` before it is stored. An unbalanced proposal is rejected at
   write time, never shown to the user.
4. **Decision.** `POST /api/approvals/{id}/decision` stops being demo-only
   (`main.py:79` currently 409s for intake workspaces). On approve:
   - write the decision event
   - recompute dependent calculations
   - produce the **after** side of the Reports comparison from the recomputed figures
   - mark the originating task done
5. **Gate.** An approval whose finding is not `verified_by == "au"` is surfaced with an explicit
   "not independently reviewed" warning. Humans may still approve it; the UI must not imply the
   auditor signed off.
6. Drop `"approvals"` from `disabled_tabs` for intake workspaces.

**Done when:** an agent run produces a pending approval, approving it changes a number in Reports,
and rejecting it records the reason.

---

## Phase 5 — Agent board — **DONE**

Step 1 went further than planned: the board was the only consumer of `kanban.tsx`, `badge-2.tsx`,
`button-1.tsx` and `avatar.tsx`, all of which arrived with the template. Once the board stopped
dragging, dnd-kit had no purpose, so 1,232 lines of unused vendor component and three dependencies
went with it. The board is built from the app's own primitives instead.

Outstanding: **the rendering has not been checked in a browser.** TypeScript, lint and the
production build pass, and the data path was proven end to end in Phase 2, but no one has looked at
the page.


1. Delete the template body of `web/src/app/board/page.tsx` (the hardcoded `columns` state at
   `:108`). Keep the `Kanban` primitives from `components/ui/kanban` — they are fine, only the data
   is fake.
2. Render `bundle.tasks`, grouped by the contract's real `Column` values —
   `queued | working | needs_you | auditor_review | done` (`models.py:18`) — not the template's
   `backlog/inProgress/review/done`.
3. Wire `components/board/TaskDrawer.tsx` (F2) to the click handler so a task opens its steps,
   tool-call budget, rationale and linked approval.
4. Drag-and-drop: either persist a column change through a real endpoint, or make cards
   non-draggable. A drag that silently reverts on the next 2s poll is worse than no drag. Default
   to **non-draggable** — the column is derived from agent state, not a human opinion.
5. `needs_you` cards link to their approval; `auditor_review` cards link to the auditor's verdict.

**Done when:** the board shows nothing at all for a workspace with no runs, and real tasks with
real progress after a run.

---

## Phase 6 — Workflows derived, not authored — **DONE**

A workflow is one coordinator run; its stages are the plan's tasks, wrapped by Plan and Report. Nothing is authored.

1. Build `Workflow` objects in the projection from the coordinator's plan and task states: one
   workflow per run, `stages` from `TaskState.status`, `progress` from the done/total ratio,
   `owner` from `TaskSpec.role`.
2. Map status → `StageState` honestly: `done → done`, `working → running`,
   `needs_evidence/blocked → human`, `queued → todo`.
3. Drop `"workflows"` from `disabled_tabs`. A workspace with no runs shows the empty state.
4. Delete the five authored workflows from the fixtures once Phase 8 regenerates them.

**Done when:** the Workflows tab is a live view of the run DAG and shows nothing before a run.

---

## Phase 7 — Fold `/cfo` in — **DONE**

The launcher is the Command center's fourth agent choice. `/cfo?run=<id>` is the run detail view, reached from the run you started. The scripted and model_preview modes left the UI: they write to the same store as a real run now, so offering them beside one invites confusing the two.

`/cfo` is a working investigation runner hidden behind a text link, and it is the only place the
five-agent workflow can be started.

1. Move the launcher into the Command center next to the existing **Investigation agent**
   selector (`SourcesPanel.tsx:129`) — one control offering CFO triage, Grants, Auditor, and the
   five-agent workflow.
2. Keep `/cfo/[runId]` as a **run detail** page: plan, events, per-task tool calls, report link.
   That view is genuinely useful and has no equivalent elsewhere.
3. Delete the standalone `/cfo` index and the two orphan links
   (`SourcesPanel.tsx:122`, `TabGate.tsx:20`).
4. Remove the `scripted` and `model_preview` modes from the UI once live runs feed the dashboard.
   Keep them in `cfo/api.py` for tests — but the user-facing mode selector goes, since a scripted
   run now writes to the same store as a real one and must not be confusable with it.

**Done when:** everything is reachable from the sidebar, and no page writes to a store no tab reads.

---

## Phase 8 — Seed sandbox and MIT from real runs — **DONE for sandbox; MIT cannot be**

All workspace state is derived from persisted records and runs. There is no alternate preloaded bundle path.

Decided: keep both workspaces, but generate their contents instead of authoring them.

1. New `api/scripts/seed_fixtures.py`:
   - create the workspace and upload authorized source records
     (7 files, already used by the starter-pack flow), commit a snapshot
   - run the five-agent workflow live
   - run the auditor
   - verify the resulting `Bundle` against the contract
2. `ap_sandbox.json` (F11): repoint `ap_tools._load` at committed records so Stack C reads the same
   snapshot as everyone else, then delete the file.
3. MIT: it is a public-document workspace with no ledger, so the same script runs document-only
   agents over the published reports and emits real page citations. Its `kind: "public"` already
   drives the right capability gating in `ingestion.coverage:541`.
4. Commit regenerated fixtures with the run ID and model that produced them recorded in the file,
   so the provenance is auditable.
5. `store._load` stays — but it now loads a *recording of a real run*, and the workspace banner says
   so with the run ID.

**Done when:** the fixtures can be regenerated by a command, and the diff of a regeneration is
reviewable.

---

## Phase 9 — Delete and correct — **DONE**

Stack C is gone: 1,700 lines and 87 tests covering code no HTTP route could reach, plus `store.py`'s write API, whose only callers were those tools. Phase 8 forced the decision — Stack C reads its own parallel fixture and depends on the authored file's ID sequences, so it cannot survive the recording. `POST /api/demo/{action}` is deleted rather than finished. The README's L01–L13 claim now names the four invariants that exist, and its stale "live coordinator mode remains blocked" line is gone.

1. `POST /api/demo/{action}` (F12): implement `inject_issue` / `add_evidence` / `next_month` against
   the real pipeline, or delete the endpoint and the `TODO(workflows)` comment. **Recommend
   delete** — a demo-only mutation path is exactly the kind of thing this branch exists to remove.
2. `api/scripts/ask_ap_agent.py`, `ask_auditor.py`: keep only if Stack C survives Phase 8; they are
   the only non-test callers of `run_loop`.
3. README (F13): correct "invariants L01–L13" to the four that exist, and delete the stale
   "live coordinator mode remains blocked until specialist and auditor adapters are registered"
   claim — `cfo_factory.py:13` registers them.
4. README: the "What's implemented" section is written against the pre-merge state. Rewrite it from
   the Phase 1–8 result.
5. `TabGate.tsx`: its copy hardcodes assumptions about which tabs are off. Rewrite against the
   derived `disabled_tabs`.
6. Grep for any remaining component that renders a literal number, name or date. Acceptance: no
   `.tsx` outside `components/ui/` contains a hardcoded money value or person's name.

---

## Phase 10 — Minimum calculators for AP and grants (F14) — **DONE**

`accounting/ap.py` and `accounting/grants.py`. The three-way-match variance in the plan is not built and cannot be: intake has no purchase-order or goods-receipt role, only references carried on an invoice, so the modules test whether support is referenced and never whether the referenced document agrees on amount. The payoff is visible in the new recording, which carries a priced, auditor-verified AP finding — impossible before this.

Without this, AP and grants claims can never carry an amount, so the Auditor must reject every
substantiated AP claim (`agents/team.py` rejects a substantiated claim with no calculation) — the
five-agent smoke runs already return zero accepted claims for exactly this reason.

1. `accounting/ap.py`: duplicate-payment exposure, three-way-match variance (PO vs receipt vs
   invoice), unsupported-invoice total. Integer cents, same `PayrollCalculation` shape as
   `accounting/payroll.py:30`.
2. `accounting/grants.py`: award ceiling excess and outside-window charges already exist in
   `payroll.py:112,134` — lift them into a grants module that does not require payroll records.
3. Register both in the calculation inventory the coordinator publishes, so `EvidenceTools.calculate`
   can reach them.

**Done when:** a five-agent run can produce at least one accepted, substantiated, priced AP claim.

---

## Sequencing

Phase 1 unblocks 2. Phase 2 unblocks 3, 5, 6. Phases 4 and 10 are independent of each other and can
run in parallel once 2 lands. Phase 8 must come last — it records whatever the pipeline produces,
so it is only worth running when the pipeline is final.

```
1 ──► 2 ──┬──► 3 ──┐
          ├──► 5   ├──► 8 ──► 9
          ├──► 6   │
          ├──► 4 ──┘
          └──► 7
    10 ────────────┘
```

Suggested order if working alone: 1, 2, 5, 3, 10, 4, 6, 7, 8, 9. Phase 5 early because it is the
most visible fake thing and the cheapest real win.

## Verification

Each phase is done when `uv run pytest` still passes (baseline: **282 passed, 9 skipped**) and
`bun run build` + lint pass. Phases 3, 4 and 8 additionally need a live run against a committed
snapshot, since they depend on model output the offline tests stub.

Add as we go:
- a test that no `Bundle` is constructed outside `projection.py`
- a test that a `Finding.amount_cents` is never set without a backing `Calculation`
- a test that every proposed journal is balanced before it is stored
- a test that opens a `user_version = 2` database and reads it without loss
