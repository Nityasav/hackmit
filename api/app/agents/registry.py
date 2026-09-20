"""The finance organization, as data.

Twenty-two agents differ by prompt, tools, schema and budget — not by code. One
runtime (`runtime.py`) executes any of them, and the graph is built from this registry
at import time, so the topology, the documentation and the data the Books screen asks
for cannot drift apart.

Three rules this file enforces, at import:

- **Every declared input is a requirement Books asks for.** `check_registry()` compares
  `requires` against `requirements.py` in both directions, so an agent cannot depend on
  data nobody was asked to supply, and a requirement cannot name an agent that does not
  exist.
- **Attenuation.** A subagent's tool and role access must be a subset of its parent's.
  Delegation narrows authority; it never widens it.
- **No agent reviews itself.** A `reviewer` must be a different agent, and reviewers are
  drawn from the audit and close-review side of the organization.

`llm` marks whether a model runs in the hot path. Roughly half of these are deterministic
work an agent supervises: B3 reads the general ledger and computes statements in integer
cents, D3 assembles an evidence pack out of the event graph. Neither authors a number.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

from . import schemas
from .. import requirements

Tier = Literal["orchestrator", "worker", "subagent"]

#: Capability tiers. Every id is an environment variable so a model or price change is
#: configuration, not a code edit.
MODEL_SOL = os.getenv("AGENT_MODEL_SOL", "gpt-5.6-sol")
MODEL_TERRA = os.getenv("AGENT_MODEL_TERRA", "gpt-5.6-terra")
MODEL_LUNA = os.getenv("AGENT_MODEL_LUNA", "gpt-5.6-luna")


@dataclass(frozen=True)
class Budget:
    """What one agent may spend on one task. Enforced in code, never in a prompt.

    `usd_cents` is the binding limit: token counts vary with the records supplied, but
    money is what actually runs out. A task that would exceed any of these stops and
    says so rather than quietly returning less work.
    """

    model_calls: int = 3
    tool_calls: int = 20
    usd_cents: int = 40


@dataclass(frozen=True)
class EscalationRule:
    """When a person must decide instead of an agent.

    Thresholds live here rather than in prose so they are testable and so changing one
    is a visible edit. `confidence_below` is measured against the deterministic rubric
    in `accounting/match.py`; a model's opinion of its own certainty is never an input.
    """

    #: 0-100. Below this, a second agent or a human looks at it.
    confidence_below: int = 85
    #: Amounts at or above this always reach a person, whatever the agent concluded.
    amount_above_cents: int | None = None
    #: Named conditions that always escalate, regardless of confidence.
    on: tuple[str, ...] = ()
    #: Every conclusion goes to a person, whatever was computed. For work that cannot be
    #: scored against anything — a projection about a period that has not happened —
    #: which is a different statement from "scored, and the score was low".
    always: bool = False


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    tier: Tier
    #: What this agent is responsible for, in one line, for the UI and the prompt.
    charter: str
    parent: str | None = None
    model: str = MODEL_TERRA
    #: False when the work is deterministic and a model only narrates or judges
    #: exceptions around it.
    llm: bool = True
    tools: tuple[str, ...] = ()
    #: Requirement ids from `requirements.py`.
    requires: tuple[str, ...] = ()
    output_schema: type = schemas.AgentResult
    reviewer: str | None = None
    escalate_when: EscalationRule = field(default_factory=EscalationRule)
    budget: Budget = field(default_factory=Budget)

    @property
    def roles(self) -> tuple[str, ...]:
        """Intake roles this agent may read, derived from what it declared it needs.

        Deriving rather than declaring separately is the point: an agent cannot read a
        record type it never said it depended on, so scope and the Books ask are the
        same statement.
        """
        out = []
        for requirement_id in self.requires:
            role = requirements.BY_ID[requirement_id].role
            if role and role not in out:
                out.append(role)
        return tuple(out)


# --------------------------------------------------------------------------- #
# Level 0-1: the orchestrator
# --------------------------------------------------------------------------- #

ORCHESTRATOR = AgentSpec(
    id="orchestrator", name="Chief Financial Agent", tier="orchestrator",
    charter="Route work to the right domain, hold one consistent view of each "
            "transaction, and escalate what a person must decide.",
    model=MODEL_SOL, tools=("list_agents", "delegate", "read_records", "read_event", "summarize"),
    budget=Budget(model_calls=20, tool_calls=60, usd_cents=300),
)

# --------------------------------------------------------------------------- #
# Level 2: workers
# --------------------------------------------------------------------------- #

WORKERS = (
    AgentSpec(id="A", name="Treasurer", tier="worker", parent="orchestrator",
              charter="Operational cash: pay vendors, collect from customers, reconcile "
                      "the bank and keep the cash position current.",
              tools=("delegate", "read_records", "read_event"),
              requires=("vendors", "vendor_invoices", "payments", "customers",
                        "customer_invoices", "remittances", "bank_transactions"),
              budget=Budget(model_calls=6, tool_calls=30, usd_cents=80)),
    AgentSpec(id="B", name="Controller", tier="worker", parent="orchestrator",
              charter="Close the books and produce financial statements that tie to the ledger.",
              tools=("delegate", "read_records", "read_event"),
              requires=("chart", "opening", "ledger", "period_locks"),
              budget=Budget(model_calls=6, tool_calls=30, usd_cents=140)),
    AgentSpec(id="C", name="FP&A", tier="worker", parent="orchestrator",
              charter="Turn actuals into budgets, forecasts and explanations a board can read.",
              tools=("delegate", "read_records", "read_event"),
              requires=("chart", "ledger", "budgets", "forecasts", "headcount", "payroll"),
              budget=Budget(model_calls=6, tool_calls=30, usd_cents=120)),
    AgentSpec(id="D", name="Audit & Controls", tier="worker", parent="orchestrator",
              charter="Independently test the work of the other agents. Trust nothing "
                      "that has not been re-performed against originals.",
              model=MODEL_SOL,
              tools=("delegate", "read_records", "read_source", "read_event"),
              requires=("ledger", "approvals", "policy", "materiality_cents"),
              budget=Budget(model_calls=6, tool_calls=30, usd_cents=120)),
)

# --------------------------------------------------------------------------- #
# Level 3: subagents
# --------------------------------------------------------------------------- #

TREASURER = (
    AgentSpec(
        id="A1", name="Accounts Payable", tier="subagent", parent="A",
        charter="Match a vendor invoice to its purchase order and goods receipt, test it "
                "for duplication and policy breaches, and decide whether it may be paid.",
        tools=("read_records", "read_source", "three_way_match", "find_duplicates", "check_policy"),
        requires=("vendors", "vendor_invoices", "purchase_orders", "goods_receipts",
                  "approvals", "policy", "approval_limit_cents",
                  # The documents behind the register rows: the invoice as it was
                  # issued, and evidence that what is billed for was delivered.
                  "invoice", "service"),
        output_schema=schemas.APResult, reviewer="D2",
        escalate_when=EscalationRule(
            confidence_below=85, amount_above_cents=500_000,
            on=("duplicate_suspected", "no_purchase_order", "no_goods_receipt",
                "amount_mismatch", "vendor_changed", "self_approved")),
        budget=Budget(model_calls=3, tool_calls=20, usd_cents=40)),
    AgentSpec(
        id="A2", name="Accounts Receivable", tier="subagent", parent="A",
        charter="Track what customers owe, age it, and apply incoming cash to the right invoices.",
        tools=("read_records", "read_source", "age_receivables", "match_remittance"),
        requires=("customers", "customer_invoices", "remittances"),
        llm=True, reviewer="D2",
        escalate_when=EscalationRule(confidence_below=80, on=("ambiguous_remittance", "partial_payment",
                                                           "overpayment", "unreferenced_remittance")),
        budget=Budget(model_calls=3, tool_calls=20, usd_cents=40)),
    AgentSpec(
        id="A3", name="Bank Reconciliation", tier="subagent", parent="A",
        charter="Agree bank activity to the ledger, including payouts that arrive net of "
                "fees, refunds and chargebacks.",
        tools=("read_records", "read_source", "reconcile_bank", "decompose_payout"),
        requires=("bank_transactions", "payments", "remittances", "ledger", "processor_payouts"),
        reviewer="D2",
        escalate_when=EscalationRule(confidence_below=80, on=("unmatched_difference", "duplicate_posting")),
        budget=Budget(model_calls=3, tool_calls=24, usd_cents=48)),
    AgentSpec(
        id="A4", name="Cash Management", tier="subagent", parent="A",
        charter="Maintain the near-term cash position and flag a shortfall before it happens.",
        llm=False, model=MODEL_LUNA,
        tools=("read_records", "project_cash"),
        requires=("bank_transactions", "vendor_invoices", "customer_invoices", "payroll"),
        budget=Budget(model_calls=2, tool_calls=16, usd_cents=12)),
)

CONTROLLER = (
    AgentSpec(
        id="B1", name="Month-End Close", tier="subagent", parent="B",
        charter="Run the close checklist, hold its state across days, and decide when the "
                "period is ready to lock.",
        model=MODEL_SOL,
        tools=("read_records", "read_event", "close_checklist", "delegate"),
        requires=("chart", "opening", "ledger", "period_locks", "fiscal_year_end", "close_target_day"),
        reviewer="B4",
        escalate_when=EscalationRule(confidence_below=90, on=("unreconciled_account", "missing_entry")),
        budget=Budget(model_calls=8, tool_calls=40, usd_cents=120)),
    AgentSpec(
        id="B2", name="Accruals & Adjustments", tier="subagent", parent="B",
        charter="Recognize what the period incurred but was not billed for, and support "
                "every adjustment with evidence.",
        tools=("read_records", "read_source", "propose_journal"),
        requires=("ledger", "vendor_invoices", "purchase_orders", "goods_receipts", "contract"),
        reviewer="B4",
        escalate_when=EscalationRule(confidence_below=85, amount_above_cents=1_000_000,
                                     on=("estimate_without_evidence",)),
        budget=Budget(model_calls=3, tool_calls=24, usd_cents=48)),
    AgentSpec(
        id="B3", name="Financial Reporting", tier="subagent", parent="B",
        charter="Produce the income statement, balance sheet and cash flow from the ledger, "
                "and flag anything that does not tie.",
        # A model must never author a financial statement. The arithmetic is deterministic
        # and the agent's only job is to notice when it fails to tie.
        llm=False, model=MODEL_LUNA,
        tools=("read_records", "build_statements"),
        requires=("chart", "opening", "ledger", "fiscal_year_end"),
        reviewer="B4",
        budget=Budget(model_calls=2, tool_calls=16, usd_cents=12)),
    AgentSpec(
        id="B4", name="Close Review", tier="subagent", parent="B",
        charter="Review the close independently. Reject work that is not supported and "
                "escalate what is material.",
        model=MODEL_SOL,
        tools=("read_records", "read_source", "read_event", "reperform"),
        requires=("ledger", "approvals", "materiality_cents"),
        escalate_when=EscalationRule(confidence_below=95, on=("unsupported_entry", "material_difference")),
        budget=Budget(model_calls=4, tool_calls=30, usd_cents=100)),
)

FPA = (
    AgentSpec(
        id="C1", name="Budgeting", tier="subagent", parent="C",
        charter="Maintain the approved operating budget and the assumptions behind it.",
        tools=("read_records", "roll_up"),
        requires=("chart", "budgets", "payroll", "headcount", "budget"),
        budget=Budget(model_calls=3, tool_calls=20, usd_cents=40)),
    AgentSpec(
        id="C2", name="Forecasting", tier="subagent", parent="C",
        charter="Maintain forward revenue, expense and cash forecasts, and explain a miss.",
        tools=("read_records", "forecast_series"),
        requires=("ledger", "customer_invoices", "forecasts", "headcount", "fiscal_year_end"),
        escalate_when=EscalationRule(confidence_below=75),
        budget=Budget(model_calls=3, tool_calls=24, usd_cents=48)),
    AgentSpec(
        id="C3", name="Variance Analysis", tier="subagent", parent="C",
        charter="Explain why actuals differ from plan, tracing each driver to the "
                "transactions that caused it.",
        tools=("read_records", "read_event", "decompose_variance"),
        requires=("chart", "ledger", "budgets", "forecasts", "budget"),
        reviewer="D2",
        escalate_when=EscalationRule(confidence_below=80, on=("unexplained_residual",)),
        budget=Budget(model_calls=4, tool_calls=28, usd_cents=64)),
    AgentSpec(
        id="C4", name="Strategic Planning", tier="subagent", parent="C",
        charter="Model multi-year scenarios. Output is a projection for a person to weigh, "
                "never a measured result.",
        model=MODEL_SOL,
        tools=("read_records", "model_scenario"),
        requires=("ledger", "budgets", "forecasts", "headcount"),
        # Nothing here can be scored against an outcome, so it always goes to a person.
        # Stated outright: a threshold of 101 would have looked equivalent and was not,
        # because a threshold is only consulted when a score exists at all.
        escalate_when=EscalationRule(always=True),
        budget=Budget(model_calls=4, tool_calls=20, usd_cents=100)),
    AgentSpec(
        id="C5", name="Board Reporting", tier="subagent", parent="C",
        charter="Assemble management and board reporting from figures that already tie to "
                "the ledger. Writes prose, never numbers.",
        tools=("read_records", "read_event", "build_report"),
        requires=("chart", "ledger", "budgets"),
        reviewer="B4",
        budget=Budget(model_calls=3, tool_calls=20, usd_cents=48)),
)

AUDIT = (
    AgentSpec(
        id="D1", name="Audit", tier="subagent", parent="D",
        charter="Sample transactions and trace them end to end, from source document to "
                "ledger and back.",
        model=MODEL_SOL,
        tools=("read_records", "read_source", "read_event", "select_sample",
               "trace_transaction", "reperform"),
        requires=("ledger", "vendor_invoices", "purchase_orders", "goods_receipts",
                  "payments", "approvals", "bank_transactions", "materiality_cents",
                  # "trace them end to end, from source document" is the charter;
                  # without these the trail stops at the register row.
                  "invoice", "service", "contract"),
        escalate_when=EscalationRule(confidence_below=90, on=("broken_trail", "missing_approval")),
        budget=Budget(model_calls=4, tool_calls=36, usd_cents=120)),
    AgentSpec(
        id="D2", name="Controls Testing", tier="subagent", parent="D",
        charter="Test whether the controls actually operated: duplicates, self-approval, "
                "post-close entries, policy breaches.",
        model=MODEL_SOL,
        # The tests are deterministic; the model judges the cases the rules cannot settle.
        llm=True,
        tools=("read_records", "read_source", "run_controls", "check_policy",
               "check_precedents"),
        requires=("vendors", "vendor_invoices", "payments", "expenses", "approvals",
                  "period_locks", "ledger", "policy", "materiality_cents"),
        escalate_when=EscalationRule(confidence_below=90, on=("control_failure",)),
        budget=Budget(model_calls=4, tool_calls=32, usd_cents=100)),
    AgentSpec(
        id="D3", name="Audit Evidence", tier="subagent", parent="D",
        charter="Assemble the defensible record of why each decision was made. Generates "
                "nothing; it collects what already happened.",
        llm=False, model=MODEL_LUNA,
        tools=("read_event", "read_decisions", "build_evidence_pack"),
        requires=(),
        budget=Budget(model_calls=1, tool_calls=24, usd_cents=8)),
    AgentSpec(
        id="D4", name="Reporting & Filing", tier="subagent", parent="D",
        charter="Assemble recurring audit and regulatory packages, and say what each is "
                "missing before a deadline.",
        tools=("read_records", "read_event", "build_report"),
        requires=("ledger", "tax_registrations", "home_jurisdiction"),
        reviewer="D1",
        budget=Budget(model_calls=3, tool_calls=20, usd_cents=48)),
)

def _with_subtree_scope(specs: dict[str, AgentSpec]) -> dict[str, AgentSpec]:
    """Give every parent at least the scope of everything below it.

    Attenuation says a delegation narrows authority. That only works if the delegator
    *has* the authority in the first place, so a parent's readable roles must cover its
    whole subtree. Deriving that here rather than restating each child's inputs on its
    parent means the invariant holds by construction: adding an input to A1 widens A and
    the orchestrator automatically, and no hand-maintained list can fall behind.

    It also keeps the Books ask honest, because a worker now names every input any of
    its children will need.
    """
    from dataclasses import replace

    def gather(agent_id: str) -> tuple[str, ...]:
        own = list(specs[agent_id].requires)
        for child in (s for s in specs.values() if s.parent == agent_id):
            for requirement_id in gather(child.id):
                if requirement_id not in own:
                    own.append(requirement_id)
        return tuple(own)

    widened = {}
    for agent_id, spec in specs.items():
        full = gather(agent_id)
        widened[agent_id] = replace(spec, requires=full) if full != spec.requires else spec
    return widened


AGENTS: dict[str, AgentSpec] = _with_subtree_scope({
    spec.id: spec for spec in (ORCHESTRATOR, *WORKERS, *TREASURER, *CONTROLLER, *FPA, *AUDIT)
})

#: Reviewers may only come from the independent side of the organization. A preparer
#: reviewing its own domain is not a review.
INDEPENDENT_REVIEWERS = frozenset({"B4", "D1", "D2"})


def children(agent_id: str) -> tuple[AgentSpec, ...]:
    return tuple(spec for spec in AGENTS.values() if spec.parent == agent_id)


def ancestry(agent_id: str) -> tuple[str, ...]:
    """From this agent up to the orchestrator."""
    chain, current = [], AGENTS[agent_id]
    while current.parent:
        chain.append(current.parent)
        current = AGENTS[current.parent]
    return tuple(chain)


def _check() -> None:
    problems: list[str] = []

    # 1. Requirements agree in both directions with what Books asks for.
    problems += requirements.check_registry(
        {spec.id: spec.requires for spec in AGENTS.values()})

    for spec in AGENTS.values():
        # 2. Structure.
        if spec.tier == "orchestrator" and spec.parent:
            problems.append(f"{spec.id}: the orchestrator has no parent")
        if spec.tier != "orchestrator":
            if spec.parent not in AGENTS:
                problems.append(f"{spec.id}: unknown parent {spec.parent!r}")
                continue
            parent = AGENTS[spec.parent]
            # 3. Attenuation: a child may not reach past its parent.
            extra_tools = set(spec.tools) - set(parent.tools) - _LEAF_TOOLS
            if extra_tools:
                problems.append(
                    f"{spec.id} claims tools its parent {parent.id} does not have: "
                    f"{sorted(extra_tools)}")
            if spec.budget.usd_cents > parent.budget.usd_cents:
                problems.append(
                    f"{spec.id} may spend more than its parent {parent.id}; a delegation "
                    "cannot widen a budget")
        # 4. Nobody reviews themselves, and reviewers are independent.
        if spec.reviewer:
            if spec.reviewer == spec.id:
                problems.append(f"{spec.id} is its own reviewer")
            elif spec.reviewer not in AGENTS:
                problems.append(f"{spec.id}: unknown reviewer {spec.reviewer!r}")
            elif spec.reviewer not in INDEPENDENT_REVIEWERS:
                problems.append(
                    f"{spec.id} names {spec.reviewer} as reviewer, which is not one of "
                    f"the independent reviewers {sorted(INDEPENDENT_REVIEWERS)}")
        # 5. A deterministic agent still needs enough budget to report what it found.
        if spec.budget.model_calls < 1 or spec.budget.usd_cents < 1:
            problems.append(f"{spec.id}: a budget of zero cannot produce a result")

    if problems:
        raise AssertionError("Agent registry is inconsistent:\n  " + "\n  ".join(problems))


#: Tools a leaf agent may hold without its parent holding them. These read evidence or
#: run deterministic calculations; none of them delegates, spends beyond the leaf's own
#: budget, or reaches outside the roles the leaf declared.
_LEAF_TOOLS = frozenset({
    "three_way_match", "find_duplicates", "check_policy", "age_receivables",
    "match_remittance", "reconcile_bank", "decompose_payout", "project_cash",
    "close_checklist", "propose_journal", "build_statements", "reperform",
    "roll_up", "forecast_series", "decompose_variance", "model_scenario",
    "build_report", "select_sample", "run_controls", "read_decisions",
    "build_evidence_pack", "read_source", "trace_transaction", "check_precedents",
})

_check()
