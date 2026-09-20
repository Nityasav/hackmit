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
- **Fixtures** — one JSON bundle per workspace in `web/src/fixtures/`, shared by both
- **Model (planned)** — provider adapter and labeled replay; no live agent adapter is connected yet

## What's implemented

Document intake is now backed by SQLite: create an institution workspace, upload CSV/TXT/Markdown,
review column mappings and validation issues, commit an immutable snapshot, inspect original source
lines, and track missing evidence. New workspaces start empty and never inherit demo findings.

The eight-tab dashboard still includes fixed demo workspaces. Live agents, full statements,
scenario correction/recomputation and learning are not implemented. Input availability is not an
audit conclusion. PDF extraction/OCR, Excel files and live financial connectors remain deferred.

## Getting started

```bash
git clone https://github.com/Nityasav/hackmit.git
cd hackmit

# UI (works offline against the bundled fixtures)
cd web && bun install && bun dev          # http://localhost:3000

# API (required for document intake; optional only for fixed demo views)
cd ../api && uv sync && uv run uvicorn app.main:app --reload --port 8000
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

SQLite stores original bytes, staged imports, accepted record revisions, snapshots and local review
events in ignored `api/data/schooltrace.sqlite3`. Set `SCHOOLTRACE_DATA_DIR` to change the local data
directory. The app is for synthetic/public data on localhost; the reviewer marker is not production
authentication. Original files stay on the machine and are not sent to a model.

The backend addition stays flat: `api/app/db.py` and `api/app/ingestion.py`; the UI is one
`SourcesPanel.tsx`. See `PROJECT_TRACKER.md` for verified scope and the next integration task.

## Repo map

| Path | What's in it |
| --- | --- |
| `web/` | The dashboard: 8 tabs plus an MIT / Sandbox workspace switcher |
| `web/src/fixtures/` | One JSON bundle per workspace, shared by web and api |
| `api/` | Accounting engine, document intake, HTTP API |
| `schooltrace/INGESTION_PLAN.md` | The intake design this build follows |
| `PROJECT_TRACKER.md` | Verified scope and the next integration task |

### `api/` layout

| Path | What goes here |
| --- | --- |
| `app/main.py` | HTTP endpoints |
| `app/models.py` | Pydantic mirror of the bundle contract |
| `app/store.py` | Fixed demo bundles; intake workspaces use the SQLite bundle builder |
| `app/db.py` | SQLite schema, transactions, original bytes and local events |
| `app/ingestion.py` | CSV/text parsing, mappings, validation, immutable commits, coverage |
| `app/accounting/` | Exact integer-cent math and ledger invariants L01–L13 |

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
