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
- **Model** — Claude Sonnet 5 (`claude-sonnet-5`) behind a provider adapter, plus a labeled replay adapter

## Getting started

```bash
git clone https://github.com/Nityasav/hackmit.git
cd hackmit

# UI (works offline against contracts/fixtures)
cd web && bun install && bun dev          # http://localhost:3000

# API (optional while the UI runs on fixtures)
cd ../api && uv sync
uv run uvicorn app.main:app --reload --port 8000   # docs at /docs
uv run pytest                                       # accounting invariants

# Point the UI at the API
echo 'NEXT_PUBLIC_API_URL=http://localhost:8000' > ../web/.env.local
```

## Repo map

| Path | What's in it |
| --- | --- |
| `web/` | The dashboard: 8 tabs plus an MIT / Sandbox workspace switcher |
| `api/` | Accounting engine, agents, workflows, HTTP API |
| `contracts/fixtures/` | One JSON bundle per workspace, shared by web and api |
| `schooltrace/` | The spec: product, accounting rules, agent prompts, evaluation, demo script |

### `api/` layout

| Path | Owner | What goes here |
| --- | --- | --- |
| `app/main.py` | Functionality | HTTP endpoints (see [Endpoints](#endpoints)) |
| `app/models.py` | Functionality | Pydantic mirror of the bundle contract |
| `app/store.py` | Functionality | Bundle state. Fixture-seeded today, SQLite-backed next |
| `app/accounting/` | Functionality | Exact integer-cent math and ledger invariants L01–L13 |

## The data contract

The seam between the four workstreams. **Change these three together:**

| File | Owner of the change |
| --- | --- |
| `contracts/fixtures/*.json` | whoever adds the data |
| `web/src/lib/types.ts` | UI |
| `api/app/models.py` | Functionality |

If you change a field, say so in the team channel before you push. Everything else can move independently.

### The bundle

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

### Endpoints

| Endpoint | Behavior |
| --- | --- |
| `GET /api/health` | liveness |
| `GET /api/workspaces/{ws}/bundle` | everything the dashboard renders. The web app polls every 2s |
| `POST /api/approvals/{id}/decision` | `{workspace, decision}` → updated bundle |
| `POST /api/demo/{action}` | `reset`, `inject_issue`, `add_evidence`, `next_month` |

## Rules we build to

1. **Money is integer cents.** `amount_cents: 400000` is $4,000.00. Never float.
   `api/app/accounting/money.py` is the only place that does arithmetic on amounts, and the UI is the only
   place that formats them.
2. **Only a human decides an approval.** Agents propose; `POST /api/approvals/{id}/decision` is the one path
   that applies a change.
3. **Every agent action emits a `Decision`** (see `api/app/models.py`) so it appears in the Reasoning log.
   Concise decision records only, never raw chain-of-thought (spec.md §8).
4. **Every finding carries evidence**, and every amount traces to a calculation ID. No bare numbers.
5. **Task columns map to spec statuses**: `queued → queued`, `running → working`, `needs_evidence → needs_you`,
   `submitted → auditor_review`, `review_accepted → done`.
6. **`example: true` on ablation** means the numbers are placeholders. Remove it only when the evaluator
   wrote them (DATA_AND_EVALUATION.md §9).
7. **The answer key stays out of reach.** Evaluator truth files must live outside anything the tool gateway
   can read.

## Honesty rules we hold ourselves to

All institutions and transactions in the sandbox are fictional. The MIT tab shows MIT's **published** audit
reports only, read-only, with page citations; we do not have MIT's ledger and make no claims beyond what those
reports state. Measured numbers come from the evaluator, never from a slide.

## Team

- [Nityasav](https://github.com/Nityasav) · [hppddub](https://github.com/hppddub) · Maxim · Stanley
