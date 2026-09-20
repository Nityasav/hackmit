"""What the agents need, and therefore what Books asks for.

One registry, read by three places that would otherwise drift:

- **Books** renders an ask for every unsatisfied requirement, so a person is never
  expected to guess which file unlocks which analysis.
- **The agent registry** (phase 2) declares `requires=(...)` against these ids, and
  `check_registry()` fails at import if an agent depends on something nobody asks for.
- **The orchestrator** refuses to dispatch an agent whose inputs are missing, and says
  which upload would unblock it rather than letting the agent invent an answer.

A requirement is satisfied by a committed CSV of a given role, a committed document, or
a workspace setting answered in a form. Settings exist because some inputs are a single
value — a materiality threshold, a home jurisdiction — and asking for a one-row CSV would
be worse than asking a question.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from . import roles

Kind = Literal["csv", "document", "setting"]


@dataclass(frozen=True)
class Requirement:
    id: str
    label: str
    kind: Kind
    #: What becomes possible once this is supplied. Shown under the ask in Books.
    unlocks: str
    #: Registry ids of the agents blocked without it.
    needed_by: tuple[str, ...]
    #: Intake role for csv/document requirements.
    role: str | None = None
    #: Workspace setting key for setting requirements.
    setting: str | None = None
    #: How a setting is captured, so Books can render the right control.
    control: Literal["text", "money", "integer", "date", "month_day"] | None = None
    #: An optional requirement degrades an analysis; it does not block it.
    optional: bool = False
    #: Requirement ids that should be supplied first; ordering only, not enforcement.
    after: tuple[str, ...] = field(default_factory=tuple)


def _csv(rid, needed_by, unlocks, *, optional=False, after=()):
    return Requirement(id=rid, label=roles.LABELS[rid], kind="csv", role=rid,
                       unlocks=unlocks, needed_by=needed_by, optional=optional, after=after)


REQUIREMENTS: tuple[Requirement, ...] = (
    # ---- Ledger spine -----------------------------------------------------
    _csv("chart", ("orchestrator", "B", "C", "B1", "B3", "C1", "C3", "C5"),
         "Every other record is checked against this, so it comes first."),
    _csv("opening", ("orchestrator", "B", "B1", "B3"),
         "Opening position for the period. Without it a balance sheet has no starting point.",
         after=("chart",)),
    _csv("ledger", ("orchestrator", "A", "B", "C", "D", "A3", "B1", "B2", "B3", "B4", "C2", "C3", "C4", "C5", "D1", "D2", "D4"),
         "The book of record. Statements, variance and audit testing all read it.",
         after=("chart", "opening")),

    # ---- Purchase to pay --------------------------------------------------
    _csv("vendors", ("orchestrator", "A", "D", "A1", "D2"),
         "Who you owe. Also what makes duplicate-vendor testing possible."),
    _csv("vendor_invoices", ("orchestrator", "A", "B", "D", "A1", "A4", "B2", "D1", "D2"),
         "What you have been billed. The starting point for three-way matching.",
         after=("vendors",)),
    _csv("purchase_orders", ("orchestrator", "A", "B", "D", "A1", "B2", "D1"),
         "The order side of a three-way match.", after=("vendors",)),
    _csv("goods_receipts", ("orchestrator", "A", "B", "D", "A1", "B2", "D1"),
         "The delivery side of a three-way match.", after=("purchase_orders",)),
    _csv("payments", ("orchestrator", "A", "D", "A3", "D1", "D2"),
         "What actually left the company, and what bank activity is matched against.",
         after=("vendor_invoices",)),

    # ---- Order to cash ----------------------------------------------------
    _csv("customers", ("orchestrator", "A", "A2"), "Who owes you."),
    _csv("customer_invoices", ("orchestrator", "A", "C", "A2", "A4", "C2"),
         "What you have billed. Drives receivables aging and expected cash.",
         after=("customers",)),
    _csv("remittances", ("orchestrator", "A", "A2", "A3"),
         "Money received, so cash can be applied against the right invoices.",
         after=("customer_invoices",)),

    # ---- Cash -------------------------------------------------------------
    _csv("bank_transactions", ("orchestrator", "A", "D", "A3", "A4", "D1"),
         "Bank truth. Reconciliation compares this against the ledger."),
    _csv("processor_payouts", ("orchestrator", "A", "A3"),
         "Payouts arrive net of fees, refunds and chargebacks; without the breakdown a "
         "payout never reconciles to gross sales.", optional=True),

    # ---- People and spend -------------------------------------------------
    _csv("payroll", ("orchestrator", "A", "C", "A4", "C1"),
         "Usually the largest cost line, and a fixed claim on cash."),
    _csv("expenses", ("orchestrator", "D", "D2"),
         "Employee spend, where policy testing finds most exceptions.", optional=True),

    # ---- Plan -------------------------------------------------------------
    _csv("budgets", ("orchestrator", "C", "C1", "C3", "C4", "C5"),
         "The approved plan. Variance analysis is impossible without it.", after=("chart",)),
    _csv("forecasts", ("orchestrator", "C", "C2", "C3", "C4"),
         "Prior forecast, so a miss can be explained rather than just observed.",
         optional=True, after=("chart",)),
    _csv("headcount", ("orchestrator", "C", "C1", "C2", "C4"),
         "Headcount by period, so payroll can be modelled forward.", optional=True),

    # ---- Control ----------------------------------------------------------
    _csv("approvals", ("orchestrator", "A", "B", "D", "A1", "B4", "D1", "D2"),
         "Who authorized what. Self-approval and missing-approval tests read this."),
    _csv("period_locks", ("orchestrator", "B", "D", "B1", "D2"),
         "When each period closed, which is what makes a post-close entry detectable.",
         optional=True),
    _csv("tax_registrations", ("orchestrator", "D", "D4"),
         "Where you are registered and at what rate, so indirect tax can be determined "
         "per jurisdiction rather than assumed.", optional=True),

    # ---- Documents --------------------------------------------------------
    Requirement(id="policy", label="Expense and approval policy", kind="document", role="policy",
                unlocks="The rules controls testing measures against. Without it, a policy "
                        "breach can only be guessed at.",
                needed_by=("orchestrator", "A", "D", "A1", "D2")),
    Requirement(id="contract", label="Customer and vendor contracts", kind="document", role="contract",
                unlocks="Terms behind revenue and commitments, for accrual and cut-off judgments.",
                needed_by=("orchestrator", "B", "B2"), optional=True),

    # ---- Settings ---------------------------------------------------------
    Requirement(id="home_jurisdiction", label="Home tax jurisdiction", kind="setting",
                setting="home_jurisdiction", control="text",
                unlocks="Which indirect-tax rules apply by default, and which filings are expected.",
                needed_by=("orchestrator", "D", "D4")),
    Requirement(id="fiscal_year_end", label="Fiscal year end", kind="setting",
                setting="fiscal_year_end", control="month_day",
                unlocks="Period boundaries for close, statements and forecasting.",
                needed_by=("orchestrator", "B", "C", "B1", "B3", "C2")),
    Requirement(id="materiality_cents", label="Materiality threshold", kind="setting",
                setting="materiality_cents", control="money",
                unlocks="The line above which a difference is escalated rather than noted. "
                        "Reviewers and audit testing both read it.",
                needed_by=("orchestrator", "B", "D", "B4", "D1", "D2")),
    Requirement(id="approval_limit_cents", label="Payment approval limit", kind="setting",
                setting="approval_limit_cents", control="money",
                unlocks="The amount above which a payment needs a person, whatever the agent concludes.",
                needed_by=("orchestrator", "A", "A1")),
    Requirement(id="close_target_day", label="Close target business day", kind="setting",
                setting="close_target_day", control="integer",
                unlocks="What the close is measured against, so a slipping close is visible.",
                needed_by=("orchestrator", "B", "B1"), optional=True),
)

BY_ID: dict[str, Requirement] = {r.id: r for r in REQUIREMENTS}

#: Settings live inside the workspace config blob under this key.
SETTINGS_KEY = "settings"


def settings_schema() -> list[Requirement]:
    """Every setting Books may ask for, in registry order."""
    return [r for r in REQUIREMENTS if r.kind == "setting"]


def satisfied(requirement: Requirement, present_roles: set[str], settings: dict) -> bool:
    if requirement.kind == "setting":
        value = settings.get(requirement.setting)
        return value is not None and str(value).strip() != ""
    return requirement.role in present_roles


def status(config: dict, present_roles: set[str]) -> dict:
    """What is supplied, what is missing, and which agents are waiting on it.

    `present_roles` is the set of roles with at least one active committed record —
    a superseded source does not keep a requirement satisfied.
    """
    settings = config.get(SETTINGS_KEY) or {}
    items, blocked = [], {}
    for requirement in REQUIREMENTS:
        ok = satisfied(requirement, present_roles, settings)
        items.append({
            "id": requirement.id,
            "label": requirement.label,
            "kind": requirement.kind,
            "role": requirement.role,
            "setting": requirement.setting,
            "control": requirement.control,
            "optional": requirement.optional,
            "satisfied": ok,
            "unlocks": requirement.unlocks,
            "needed_by": list(requirement.needed_by),
            "after": list(requirement.after),
            "value": settings.get(requirement.setting) if requirement.kind == "setting" else None,
        })
        if not ok and not requirement.optional:
            for agent in requirement.needed_by:
                blocked.setdefault(agent, []).append(requirement.id)

    required = [i for i in items if not i["optional"]]
    return {
        "requirements": items,
        # An agent is ready when nothing mandatory it needs is missing. Optional
        # inputs narrow what it can conclude; they never gate it.
        "blocked_agents": {agent: sorted(ids) for agent, ids in sorted(blocked.items())},
        "satisfied_count": sum(1 for i in required if i["satisfied"]),
        "required_count": len(required),
        "note": "Requirements describe what the agents can read, not whether the books are "
                "complete. Supplying every input is not an assurance of completeness.",
    }


def check_registry(agent_requires: dict[str, tuple[str, ...]]) -> list[str]:
    """Problems between the agent registry and this one, as readable lines.

    Called from the agent registry's import so a dependency on data nobody asks for
    fails immediately rather than at run time, in front of a user, as an empty result.
    """
    problems = []
    for agent, required in sorted(agent_requires.items()):
        for requirement_id in required:
            if requirement_id not in BY_ID:
                problems.append(f"{agent} requires {requirement_id!r}, which is not a known requirement")
            elif agent not in BY_ID[requirement_id].needed_by:
                problems.append(
                    f"{agent} requires {requirement_id!r} but is not listed in its needed_by, "
                    "so Books would never say which agent the upload unblocks")
    for requirement in REQUIREMENTS:
        for agent in requirement.needed_by:
            if agent not in agent_requires:
                problems.append(f"{requirement.id} names unknown agent {agent!r} in needed_by")
    return problems


def _self_check() -> None:
    """Every csv/document requirement must name a role the intake vocabulary accepts."""
    for requirement in REQUIREMENTS:
        if requirement.kind == "setting":
            assert requirement.setting and requirement.control, requirement.id
            continue
        assert requirement.role in roles.FIELDS or requirement.role in roles.DOCUMENT_ROLES, \
            f"{requirement.id} names role {requirement.role!r}, which intake does not accept"
        for predecessor in requirement.after:
            assert predecessor in BY_ID, f"{requirement.id} orders itself after unknown {predecessor!r}"


_self_check()
