# SchoolTrace build package

An evidence-backed, multi-agent financial detective for educational institutions.

This package specifies a hackathon prototype, not a completed application. All demonstration institutions, financial data, grant conditions, and monetary examples are fictional. Sources inform the design; they do not certify compliance.

Showcase exception: [DEMO.md](DEMO.md) now begins with MIT's actual public audit reports and a published financial schedule. Those sourced records are real; injected transactions and monthly investigations remain explicitly synthetic. The demo supports labeled recorded runs and working interactive calculations for speed.

## Start here

1. Read [spec.md](spec.md) for product scope, architecture, agent behavior, context graph, controls, and acceptance criteria.
2. Give a coding agent [BUILD_PROMPT.md](BUILD_PROMPT.md), with this entire directory attached or available in its workspace.
3. Follow [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for milestones and resources.
4. Use [ACCOUNTING_CONTROLS.md](ACCOUNTING_CONTROLS.md) for accounting rules and worked examples.
5. Implement [DATA_AND_EVALUATION.md](DATA_AND_EVALUATION.md) for synthetic data, hidden issues, and the memory experiment.
6. Load role instructions from [AGENT_PROMPTS.md](AGENT_PROMPTS.md).
7. Present with [DEMO.md](DEMO.md), consulting [SOURCES.md](SOURCES.md) for grounding and limitations.

## Product in one sentence

SchoolTrace follows money across payroll, purchases, grants, and financial records, coordinates specialist investigations, and delivers a reviewable remediation plan before external audit fieldwork.

## Core design decisions

- One fictional school district, two monthly periods, USD, and an explicitly simplified accrual management ledger for the MVP.
- Five reasoning agents; arithmetic, ledger validation, authorization, and state transitions are deterministic services.
- A typed, temporal context graph stores source relationships, investigation hypotheses, approved decisions, and output dependencies.
- SQL is the financial source of truth; the graph is a reconstructible projection, not a competing ledger.
- Human-reviewed memory can improve later investigations, but is scoped, versioned, revocable, and checked against current evidence.
- Corrections are simulated in a separate approved scenario. No real payments, payroll changes, ERP postings, or external communications.
- Success is measured against hidden ground truth, including false positives and negative transfer from memory.

The core demo is an investigation, not a chatbot dashboard: new evidence changes an agent's next action, a reviewer rejects an unsupported claim, and an approved correction propagates consistently to every affected output.
