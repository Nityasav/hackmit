# SchoolTrace build package

An evidence-backed, multi-agent financial detective for educational institutions.

This package specifies a hackathon prototype, not a completed application. All demonstration institutions, financial data, grant conditions, and monetary examples are fictional. Sources inform the design; they do not certify compliance.

Showcase exception: [DEMO.md](DEMO.md) now begins with MIT's actual public audit reports and a published financial schedule. Those sourced records are real; injected transactions and monthly investigations remain explicitly synthetic. The demo supports labeled recorded runs and working interactive calculations for speed.

## Start here

Hackathon build: about 16 hours (Sat Sep 19, ~6pm → Sun Sep 20, ~10am, 2026), 4 people split into **UI, Agent design, Workflows, and Functionality**. The owner split, checkpoints, and interfaces are in [/WORKPLAN.md](../WORKPLAN.md). The code lives in `web/` (Next.js), `api/` (FastAPI), and `contracts/` (the shared JSON seam). The approved UI prototype is `docs/design/prototype.html`.

1. Read [spec.md](spec.md) for product scope, architecture, agent behavior, context graph, UI, controls, and acceptance criteria.
2. Take your area's tasks from [/WORKPLAN.md](../WORKPLAN.md). Follow [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the 16h checkpoints and the cut list.
3. Give a coding agent [BUILD_PROMPT.md](BUILD_PROMPT.md), with this entire directory attached or available in its workspace.
4. Use [ACCOUNTING_CONTROLS.md](ACCOUNTING_CONTROLS.md) for accounting rules and worked examples.
5. Implement [DATA_AND_EVALUATION.md](DATA_AND_EVALUATION.md) for synthetic data, hidden issues, the playbook replay gate, and the memory experiment.
6. Load role instructions from [AGENT_PROMPTS.md](AGENT_PROMPTS.md).
7. Present with [DEMO.md](DEMO.md), consulting [SOURCES.md](SOURCES.md) for grounding and limitations.

## Product in one sentence

SchoolTrace is an Office of the CFO for schools, run by AI agents. It follows money across payroll, purchases, grants, and financial records, runs the finance workflows, and delivers a reviewable remediation plan before external audit fieldwork. The human CFO or controller approves every change.

## Core design decisions

- One fictional school district, two monthly periods, USD, and an explicitly simplified accrual management ledger for the MVP.
- Five reasoning agents, shown as a finance office: the CFO Agent, AP & Payments, Payroll & Budget, Grants & Compliance, and the Internal Auditor. Arithmetic, ledger validation, authorization, and state transitions are deterministic services.
- The AI must be visible in the UI. The agent board shows live tasks, every agent action leaves a structured decision record in the Reasoning log, and the Learning tab shows what the agents learned.
- Learning (RSI) means agent-written playbooks. Each one must pass a replay of prior months and get human approval before use. The agents never edit their own prompts or fine-tune.
- A typed, temporal context graph stores source relationships, investigation hypotheses, approved decisions, and output dependencies.
- SQL is the financial source of truth; the graph is a reconstructible projection, not a competing ledger.
- Human-reviewed memory can improve later investigations, but is scoped, versioned, revocable, and checked against current evidence.
- Corrections, payment batches, and payroll reallocations are simulated in a separate approved scenario. Agents prepare them and a human releases them. There are no real payments, payroll changes, ERP postings, or external communications.
- Success is measured against hidden ground truth, including false positives and negative transfer from memory.

The core demo is an investigation, not a chatbot dashboard. New evidence changes an agent's next action, a reviewer rejects an unsupported claim, and an approved correction propagates consistently to every affected output. Viewers watch each step happen on the Agent board and can open its reasoning in the Reasoning log.
