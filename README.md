# Sherlock

Brand: Sherlock — follow the evidence. The magnifying-glass mark is shared by the
site header, sidebar, login and favicon. Existing `SCHOOLTRACE_*` environment
variables, database filenames, reviewer header, session cookie and extraction
schema IDs remain compatibility identifiers; renaming the product does not reset
saved workspaces or break the partner model contract.

An **Office of the CFO for schools, run by AI agents.** Our project for [HackMIT 2026](https://hackmit.org)
(Maximor track).

## What it does

Schools lose track of money across payroll, purchasing and grants, and only find out at audit time.
Sherlock puts a team of five AI agents on the books: they investigate, cite their evidence, re-check each
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

### Laptop-first guided demo

Open **http://localhost:3000/** and choose **Try the guided financial scan**. This
creates and commits a fresh fictional September workspace, runs actual deterministic
record checks and opens a guided review. Inspect the repeated invoice, open source
lines, assign follow-up, add the withheld service memo, rescan and export the director
briefing. No API call is made by this button. Optional live five-agent review is a
separate, clearly labelled action on `/cfo`; its accepted claims flow into the same
Findings/Reports view. Standalone candidates remain explicitly unverified.

New uploaded-workspace pages use the shared snapshot review feed. Fixed example
workspaces remain labelled demonstrations. Proposal approval records a human decision
only: it does not post a journal, release a payment or certify compliance.

See [DEMO_IMPLEMENTATION.md](DEMO_IMPLEMENTATION.md) for test results, the demo script,
optional role/workspace access configuration and remaining production gates.

Document intake is now backed by SQLite: create an institution workspace, upload CSV/TXT/Markdown,
review column mappings and validation issues, commit an immutable snapshot, inspect original source
lines, and track missing evidence. A bounded CFO agent can inspect that snapshot through read-only tools
and produce source-cited candidate findings and specialist tasks. New workspaces start empty and never inherit demo findings.

The dashboard still includes fixed demo workspaces. Connected five-agent investigation,
invoice duplicate candidates, expense budget variance, payroll/grant checks and human
follow-up are implemented within the fictional profile. Full statements, structured
three-way matching, automatic correction/posting and learning remain incomplete.
Input availability is not an audit conclusion. PDF extraction/OCR, Excel files and
live financial connectors remain deferred.

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

This intake/triage slice uses `db.py`, `ingestion.py`, and `agents/cfo.py`; its UI lives in
`SourcesPanel.tsx`. The separately merged `app/cfo/` coordinator and `/cfo` page provide a scripted
multi-agent harness and adapter interfaces. Their `/api/cfo/runs` endpoint is distinct from the live
snapshot-triage endpoint: live coordinator mode remains blocked until specialist and auditor adapters
are registered. Triage suggestions do not automatically dispatch those agents. `OPENAI_MODEL` configures
triage; `CFO_MODEL` configures the coordinator's opt-in model preview. Neither path implements the planned
fine-tuned document extractor. See `PROJECT_TRACKER.md` for verified scope and the next integration task.

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

### Web login configuration

The web dashboard requires Supabase sign-in. Set `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_ANON_KEY` in ignored `web/.env.local`, then restart the web
server (rebuild for production). Use the publishable/anon key, never a service-role
key. Without configuration, the app returns a setup message with HTTP 503 and
does not bypass authentication. Supabase web login and the optional local API
accounts are separate; this is still a laptop demo, not end-to-end hosted tenant
authorization.

- [Nityasav](https://github.com/Nityasav) · [hppddub](https://github.com/hppddub) · Maxim · Stanley
## Documents, continuous updates, and partner model training

Use **Records & overview → Keep this institution up to date** to append files to an
existing institution, inspect snapshot changes and rescan. For PDFs/images use
**Documents & model improvement** (`/documents`, or Learning for an intake workspace).
Originals, document versions, OCR revisions, corrections and source citations are
preserved. Accepted extraction remains staged until a human commits validated intake.

The Document lab also freezes authorized training/evaluation datasets, exports JSONL
and manifests, benchmarks local model candidates and gates human promotion/rollback.
Your partner supplies the trained weights and local inference endpoint; none are
silently installed or trained. Full handoff: `EXTRACTION_IMPLEMENTATION.md`.
