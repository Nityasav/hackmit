# Agents (owner: Agent design)

Specialist agents plug into the CFO coordinator through `app/cfo/ports.py`. The
coordinator owns scheduling, budgets, the evidence gateway and the review gate;
an agent here owns judgement only.

| File | Status |
| --- | --- |
| `payroll.py` | **Implemented** — Payroll & Budget specialist (`py`), OpenAI structured output |
| `model.py` | **Implemented** — bounded structured-output adapter shared by specialists |
| `prompts.py` | Payroll role prompt from `schooltrace/AGENT_PROMPTS.md`, plus shared guardrails |
| `__main__.py` | **Implemented** — run the payroll agent against one committed workspace |
| AP & Payments (`ap`) | Not started |
| Grants & Compliance (`gr`) | Not started |
| Internal Auditor | Not started — until it exists, no live claim can be accepted |

## Payroll & Budget (`py`)

Ties out payroll and tests fund allocations. The split of responsibility is the
point of the design:

- the **model** chooses what evidence to retrieve and what it means
- the **engine** (`app/accounting/payroll.py`) decides every amount
- the **auditor** reperforms that same amount through the same code

So a claim carries a `calculation_id`, never a number the model wrote. Amounts
are integer cents, and a fund reclassification always reports a zero cash delta.

Each attempt is two bounded model calls:

1. **Evidence selection** — pick sources and calculations from the delegated
   scope, within the evidence-call allowance the coordinator granted.
2. **Findings** — draw claims strictly from what came back.

The adapter then drops any claim that cites unretrieved evidence, names a
calculation it did not run, states a currency amount in prose, or is marked
`substantiated` without an exception in the engine's result. Dropped claims
become visible notes, not silent omissions, and never reach the coordinator as
boundary violations that would fail the whole task.

Evidence selection deliberately reads award, policy and service documents
alongside the CSVs: they carry the criterion an allocation is tested against,
and an amount tested against no criterion supports nothing.

### Configuration

```powershell
$env:SPECIALIST_MODEL = '<structured-output-model-id>'   # falls back to CFO_MODEL
# OPENAI_API_KEY is read from the server environment, never a NEXT_PUBLIC_* variable.
```

`SPECIALIST_PROVIDER` (`openai` or `local`) and `SPECIALIST_LOCAL_BASE_URL` fall
back to their `CFO_*` equivalents, so one configuration serves both. The local
path accepts loopback hosts only and passes a dummy credential; the hosted key
is never forwarded to it.

### Running it against real records

A full live CFO run also needs `ap`, `gr` and the auditor, so the payroll agent
has its own entry point for real records in the meantime:

```powershell
uv run --extra cfo python -m app.agents ws-0123456789abcdef
```

It uses the real intake snapshot, the real evidence gateway with real budgets
and a real model call. Nothing is approved, posted or written back, and the
claims it prints have **not** been independently reviewed.

### What it will not do

- assert an amount the accounting engine did not produce
- read an allocation percentage out of a document's prose — that needs a
  structured allocation record, and the agent asks for one instead
- treat a document's embedded instruction as anything but quoted text
- approve, post, pay or apply anything

## Reasoning log

Every action emits a `Decision` (see `app/models.py`): when, how (tool calls),
why, alternatives, memory checks and outcome. The CFO run's event stream already
records each specialist tool call, its locator and a content digest.
