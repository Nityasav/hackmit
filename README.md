# SchoolTrace

An **Office of the CFO for schools, run by AI agents.** Our project for [HackMIT 2026](https://hackmit.org)
(Maximor track).

## What it does

Schools lose track of money across payroll, purchasing and grants, and only find out at audit time.
SchoolTrace puts a team of five AI agents on the books: they investigate, cite their evidence, re-check each
other, and hand you a decision. You approve, and every affected report updates at once.

- **CFO Agent** plans the work and writes the briefing and the close pack
- **AP & Payments** traces invoices, POs, receipts and payment batches
- **Payroll & Budget** ties out payroll and tests fund allocations
- **Grants & Compliance** tests charges against the award terms
- **Internal Auditor** re-reads the sources and redoes the math, and rejects claims that don't hold up

Two things make it more than a dashboard:

1. **You can see why.** Every action emits a decision record: when, how (the tool calls), why, and what it
   chose against. The Reasoning log makes that browsable across months.
2. **It gets better, safely.** Agents write **playbooks** from repeat cases. A playbook only takes effect if a
   **replay of past months adds zero false positives** and you approve it, and it is retired when the contract
   behind it changes.

The math is not the model's: amounts come from a deterministic engine in integer cents. Agents propose,
humans approve, and payments and payroll are simulated.

## How it works

```
CSV + documents ──► import, hash, normalize ──► SQLite ──► deterministic accounting engine
                                                    │              │
                                                    ▼              ▼
                                              context graph ──► typed tool gateway
                                                                   │
                                                          CFO Agent + 4 specialists
                                                                   │
                                                          Internal Auditor review
                                                                   │
                                                       your approval ──► recompute ──► reports
```

## Tech stack

- **web/** — Next.js 16 (App Router), TypeScript, Tailwind v4, bun
- **api/** — FastAPI, Python 3.12+, uv, SQLite
- **contracts/** — one JSON bundle per workspace, shared by both
- **Model** — live CFO, Grants & Compliance and Internal Auditor use the OpenAI Responses API; local extraction and other roles are planned

## What's implemented

Document intake is backed by SQLite: create an institution workspace, upload CSV/TXT/Markdown,
review column mappings and validation issues, commit an immutable snapshot, inspect original source
lines, and track missing evidence. New workspaces start empty and never inherit demo findings.

From a committed snapshot you can run the CFO, Grants or Internal Auditor agent on its own, or the
five-agent workflow: the CFO plans, AP & Payments, Payroll & Budget and Grants & Compliance
investigate in parallel, and the Internal Auditor re-reads every cited original and reperforms every
calculation before a claim may be reported. What survives that review reaches the dashboard through
one projection layer (`app/projection.py`), which is the only module that builds a bundle.

Every tab is fed from it: findings with evidence trails that open onto the committed original, tasks
on the board with their real tool-call budgets, workflows derived from the run's own task graph,
KPIs and a report the run published, decisions in the reasoning log, and proposals waiting in
Approvals. A finding carries an amount only when `app/accounting/` produced one and the auditor
reperformed it; a proposal contains a journal only when the committed records name both funds.
Approving one recomputes the report's before and after in exact cents.

Not implemented: the Learning tab's playbooks and replay gate, full financial statements, and any
posting of an approved change to a real system — an approval records a decision, it does not move
money. Input availability is not an audit conclusion. PDF extraction/OCR, Excel files and live
financial connectors remain deferred.

## Getting started

```bash
git clone https://github.com/Nityasav/hackmit.git
cd hackmit

# UI (works offline against the bundled fixtures)
cd web && bun install && bun dev          # http://localhost:3000

# API (required for document intake; optional only for fixed demo views)
cd ../api && uv sync
# Put OPENAI_API_KEY=... in api/.env (automatically loaded, ignored by Git).
# Optional in the same file: OPENAI_MODEL=gpt-5.4-mini
uv run uvicorn app.main:app --reload --port 8000
uv run pytest                              # accounting invariants

# Point the UI at the API
echo 'NEXT_PUBLIC_API_URL=http://localhost:8000' > ../web/.env.local
```

### Try document intake

Run the API and UI, then open **Command center → New institution**. Use synthetic USD data and
September 1–30, 2026 to try the included pack. Expand **Try a fictional September input pack**,
click **Use starter pack**, then **Preview import → Confirm & commit records**. The service record
is deliberately omitted; download it from the sample list and upload it with the **Service evidence**
role to fill the gap. You can attach it to a missing-evidence request after committing it.

Intake automatically connects to `http://localhost:8000`, even when demo views use offline fixtures.
`NEXT_PUBLIC_API_URL` overrides the URL and also enables API polling for demo views. Restart the web
server after changing environment variables. No model key is needed for intake.

SQLite stores original bytes, staged imports, accepted record revisions, snapshots, local review events
and agent runs in ignored `api/data/schooltrace.sqlite3`. Set `SCHOOLTRACE_DATA_DIR` to change the local
data directory. The app is for synthetic/public data on localhost; the reviewer marker is not production
authentication. Imports stay local until you explicitly click **Run CFO triage**; that action sends source
spans and normalized records selected by the agent's scoped tools to the configured OpenAI model.

After committing records, choose **CFO Agent** or **Grants & Compliance agent** in the Command center's
**Investigation agent** selector, then run it. Grants reviews supplied terms, payroll service periods and
award ceilings, with deterministic payroll-subset totals—not a full grant expenditure schedule or
compliance certification. `GRANTS_MODEL` optionally overrides the default model. Candidate findings link to the
original lines; suggested evidence can be added to the existing request queue. Runs are saved with
their snapshot and become visibly stale after new imports. CFO and Grants findings coexist. Choose
**Internal Auditor agent** after either preparer runs to review up to four exact findings against fresh
source reads and reperformed calculations. Its accept/reject/needs-evidence verdicts are bounded claim
reviews—not financial approvals or audit opinions. The UI shows remaining unreviewed findings and
warns when a preparer rerun makes a review historical. `AUDITOR_MODEL` optionally overrides the model.
Follow-up tasks are proposals, not automatically running agents. Training
and the local extraction model remain future work.

The same selector's fourth choice, **Five-agent workflow**, runs the CFO, all three specialists and
the Internal Auditor over the committed snapshot in one go, and links to `/cfo?run=<id>` for the
plan, the events and the report. What it accepts appears in Findings, on the board, in the Reasoning
log and — where a claim is substantiated — as a proposal in Approvals.

### Regenerating the recorded workspaces

`contracts/fixtures/sandbox.json` is a recording of a real run, not an authored file:

```bash
cd api && uv run python scripts/seed_fixtures.py        # offline, no key, no cost
uv run python scripts/seed_fixtures.py --live           # real model calls
```

Offline stubs only the prose; the records, the amounts, the auditor's reperformance and the bundle
are all produced by the real code. `workspace.recorded_from` says which mode produced a recording,
and the app shows it on every page. `mit.json` is not regenerated — its source is a published PDF
hosted elsewhere and PDF extraction is not implemented.

Single-agent triage uses `db.py`, `ingestion.py` and `agents/cfo.py`; the five-agent workflow uses
`app/cfo/` with the adapters in `app/integrations/cfo_factory.py`, which register as soon as a model
provider is configured. Both write to the same database and both reach the dashboard through
`app/projection.py`. `/cfo?run=<id>` shows one run's plan, events and report. `OPENAI_MODEL` configures
triage; `CFO_MODEL` the coordinator. Neither path implements the planned fine-tuned document
extractor. See `schooltrace/REWIRING_PLAN.md` for what each phase changed and what it deliberately
left alone.

## Repo map

| Path | What's in it |
| --- | --- |
| `web/` | The dashboard: 8 tabs plus an MIT / Sandbox workspace switcher |
| `api/` | Accounting engine, document intake, the agents, HTTP API |
| `contracts/` | The shared bundle contract and the fixtures both sides read |
| `schooltrace/` | The spec: product, accounting rules, agent prompts, evaluation, demo |
| `docs/design/prototype.html` | Clickable design prototype (open it in a browser) |
| `PROJECT_TRACKER.md` | Verified scope and the next integration task |

### `api/` layout

| Path | What goes here |
| --- | --- |
| `app/main.py` | HTTP endpoints |
| `app/models.py` | Pydantic mirror of the bundle contract |
| `app/store.py` | The two recorded workspaces, loaded from `contracts/fixtures/` |
| `app/projection.py` | The only module that builds a dashboard bundle |
| `app/approvals.py` | Proposals agents make and the decisions only a human may take |
| `app/db.py` | SQLite schema, transactions, original bytes and local events |
| `app/ingestion.py` | CSV/text parsing, mappings, validation, immutable commits, coverage |
| `app/accounting/` | Exact integer-cent math; payroll, AP and grant calculations |

### Intake notes

Intake writes require `X-SchoolTrace-Reviewer: local-reviewer`, which the UI supplies. This distinguishes
an intentional local reviewer operation; it is not authentication. Keep the server on loopback and use
synthetic/public records. Unknown workspaces and cross-workspace source IDs return 404.

Original uploads are immutable SQLite BLOBs, so a failed transaction cannot leave a DB/file-storage
mismatch. Parsing is synchronous and bounded for the small local demo. Staging, validation and commit
are atomic, persisted operations; a crash rolls back the active operation and previously saved previews
can be resumed. There is no extra worker service or queue yet.

CSV roles: chart, opening, ledger, payroll, grants, budget, invoice. Text roles: service, policy, document.
Amounts are exact decimal strings (major units) or integer minor units selected per file. Dates are
YYYY-MM-DD; opening balances are dated at the start of the period before activity. Header mapping is
explicit; canonical optional columns are recognized by name. Stable source IDs are required for CSV
records. Unsupported or malformed inputs never become accepted financial records.

No corrections, full report recomputation, live agent execution or automatic evidence verification are
performed by importing. Evidence attachment records a scoped resumption event for the future runtime.

## Rules we build to

1. **Money is integer cents.** Never float. `api/app/accounting/money.py` owns parsing and allocation
   helpers; ingestion sums integer values to validate controls. The UI is the only place that formats.
   Four ledger invariants are enforced today — L01 (debits equal credits), L02 (one side per line),
   L07 (payroll subledger ties to the ledger) and L11 (an allocation's parts sum to the whole).
   The rest of L01–L13 are specified in `schooltrace/`, not implemented.
2. **Only a human decides an approval.** Agents propose; `POST /api/approvals/{id}/decision` is the one
   path that applies a change.
3. **Every agent action emits a `Decision`** (see `api/app/models.py`) so it appears in the Reasoning log.
4. **The answer key stays out of reach.** Evaluator truth files live outside anything the tool gateway
   can read.

## Honesty rules we hold ourselves to

All institutions and transactions in the sandbox are fictional. The MIT tab shows MIT's **published** audit
reports only, read-only, with page citations; we do not have MIT's ledger and make no claims beyond what those
reports state. Measured numbers come from the evaluator, never from a slide.

## Team

- [Nityasav](https://github.com/Nityasav) · [hppddub](https://github.com/hppddub) · Maxim · Stanley
