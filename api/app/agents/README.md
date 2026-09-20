# Agents

Three implementations currently live here, built independently on separate branches and merged
without being unified yet. All three reached working agent behaviour at roughly the same time from
different directions. Consolidate before the next milestone — see PROJECT_TRACKER.md.

**Direct-run family** (`cfo.py`, `grants.py`, `auditor.py`): each agent runs standalone against a
snapshot with its own bounded loop, citations, and persistence. `cfo.py` is read-only triage. `grants.py`
adds the Grants & Compliance agent (own prompt, deterministic award-window/ceiling checks). `auditor.py`
independently reviews exact CFO/Grants finding IDs — fresh source reads, original-CSV reparsing, required
calculation reperformance, up to four verdicts per run (accept/reject/needs_evidence, not financial
approval; optional `AUDITOR_MODEL`/`GRANTS_MODEL` overrides). Command center lets a human select the role;
there is no automatic dispatch between these agents yet.

**Orchestrated family** (`ap_tools.py` / `ap_write_tools.py` / `au_write_tools.py` / `tool_gateway.py` /
`decision_tools.py` / `cfo_tools.py` / `run_loop.py`): a CFO that actually dispatches. `run_cfo_agent`'s
`assign_task` tool creates a real Task, hands its exact question to a named specialist (`ap` or `au`),
runs it synchronously, and keeps that Task's board state (`column`/`steps`/`progress`) derived from what
the specialist's tool calls actually did — never the model's own account of itself. AP's write tools
(`submit_finding` / `request_evidence` / `prepare_payment_batch`) and the Auditor's `submit_review` enforce
separation of duties in code: an agent can never verify its own finding, an approval can only be created
`pending`, and the auditor is refused if it tries to review its own work. `tool_gateway.py`'s per-run
budget enforcement (spec.md §8's default of 12) is shared by every role in this family. Verified against
the live OpenAI API end to end: CFO → AP files a finding → Auditor independently reviews it.

**Ports family** (`payroll.py`, `model.py`, `prompts.py`, `__main__.py`): plugs into the bounded
coordinator in `app/cfo/` through `app/cfo/ports.py`, which owns scheduling, budgets, the evidence
gateway and the review gate. Covers the Payroll & Budget role, which the other two families leave
planned. Detailed below.

Runs store concise decisions and tool metadata, never private chain-of-thought. The local extraction model
and its gated offline improvement loop are specified for a later implementation.

## Payroll & Budget (`py`, ports family)

Ties out payroll and tests fund allocations. The split of responsibility is the point of the design:

- the **model** chooses what evidence to retrieve and what it means
- the **engine** (`app/accounting/payroll.py`) decides every amount
- the **auditor** reperforms that same amount through the same code

So a claim carries a `calculation_id`, never a number the model wrote. Amounts are integer cents, and a
fund reclassification always reports a zero cash delta.

Each attempt is two bounded model calls:

1. **Evidence selection** — pick sources and calculations from the delegated scope, within the
   evidence-call allowance the coordinator granted.
2. **Findings** — draw claims strictly from what came back.

The adapter then drops any claim that cites unretrieved evidence, names a calculation it did not run,
states a currency amount in prose, or is marked `substantiated` without an exception in the engine's
result. Dropped claims become visible notes, not silent omissions, and never reach the coordinator as
boundary violations that would fail the whole task.

Evidence selection deliberately reads award, policy and service documents alongside the CSVs: they carry
the criterion an allocation is tested against, and an amount tested against no criterion supports nothing.

### Configuration

```powershell
$env:SPECIALIST_MODEL = '<structured-output-model-id>'   # falls back to CFO_MODEL
# OPENAI_API_KEY is read from the server environment, never a NEXT_PUBLIC_* variable.
```

`SPECIALIST_PROVIDER` (`openai` or `local`) and `SPECIALIST_LOCAL_BASE_URL` fall back to their `CFO_*`
equivalents, so one configuration serves both. The local path accepts loopback hosts only and passes a
dummy credential; the hosted key is never forwarded to it.

### Running it against real records

A full live `app/cfo/` run also needs `ap` and `gr` adapters and an auditor registered against
`app/cfo/ports.py`. The direct-run family's Grants and Auditor agents are not yet wired to those ports,
so the payroll agent has its own entry point for real records in the meantime:

```powershell
uv run python -m app.agents ws-0123456789abcdef
```

It uses the real intake snapshot, the real evidence gateway with real budgets and a real model call.
Nothing is approved, posted or written back, and the claims it prints have **not** been independently
reviewed.

### What it will not do

- assert an amount the accounting engine did not produce
- read an allocation percentage out of a document's prose — that needs a structured allocation record,
  and the agent asks for one instead
- treat a document's embedded instruction as anything but quoted text
- approve, post, pay or apply anything
