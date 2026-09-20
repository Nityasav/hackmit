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
- **Model** — first live CFO triage uses the OpenAI Responses API; local extraction model and remaining roles are planned

## What's implemented

Document intake is now backed by SQLite: create an institution workspace, upload CSV/TXT/Markdown,
review column mappings and validation issues, commit an immutable snapshot, inspect original source
lines, and track missing evidence. A bounded CFO agent can inspect that snapshot through read-only tools
and produce source-cited candidate findings and specialist tasks. New workspaces start empty and never inherit demo findings.

The eight-tab dashboard still includes fixed demo workspaces. The other four live agents, live independent review, full statements,
scenario correction/recomputation and learning are not implemented. Input availability is not an
audit conclusion. PDF extraction/OCR, Excel files and live financial connectors remain deferred.

## Getting started

```bash
git clone https://github.com/Nityasav/hackmit.git
cd hackmit

# UI (works offline against contracts/fixtures)
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

After committing records, use **Run CFO triage** in the Command center. Candidate findings link to the
original lines; suggested evidence can be added to the existing request queue. Runs are saved with
their snapshot and become visibly stale after new imports. Follow-up specialists are proposed tasks,
not running agents. Training and the local extraction model remain future work.

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
| `api/` | Accounting engine, agents, workflows, HTTP API |
| `contracts/` | The shared data contract and fixtures |
| `schooltrace/` | The spec: product, accounting rules, agent prompts, evaluation, demo script |
| `docs/design/prototype.html` | Clickable design prototype (open it in a browser) |
| `WORKPLAN.md` | Who builds what, in what order, for the 16 hours left |

## Honesty rules we hold ourselves to

All institutions and transactions in the sandbox are fictional. The MIT tab shows MIT's **published** audit
reports only, read-only, with page citations; we do not have MIT's ledger and make no claims beyond what those
reports state. Measured numbers come from the evaluator, never from a slide.

## Team

- [Nityasav](https://github.com/Nityasav) · [hppddub](https://github.com/hppddub) · Maxim · Stanley
