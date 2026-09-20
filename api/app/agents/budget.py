"""What a run is allowed to spend, metered in integer cents.

Token counts are the wrong unit to bound an agent organization with: they vary with how
many records were uploaded, and nobody's credit balance is denominated in them. Money is
what runs out, so money is what this module counts.

Three rules:

- **Integer cents, ceiling-rounded.** Cost is computed with integer arithmetic and
  rounded *up*, so the meter never reports less than was actually spent. A budget that
  rounds down overspends by exactly as much as it rounds.
- **Charge before the call, reconcile after.** A call is refused when its worst case
  would breach a cap. The estimate is replaced by the provider's reported usage once the
  call returns, so the meter tracks reality rather than the guess.
- **Fail closed.** Exceeding a cap raises. It never silently truncates the work and
  returns a thinner answer, because a thinner answer is indistinguishable from a
  complete one to whoever reads it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

#: Cents per million tokens, as integers. Observed September 2026; every value is an
#: environment variable because a price change must not require a deploy.
PRICES: dict[str, tuple[int, int]] = {
    "gpt-5.6-sol": (int(os.getenv("PRICE_SOL_IN", "400")), int(os.getenv("PRICE_SOL_OUT", "2000"))),
    "gpt-5.6-terra": (int(os.getenv("PRICE_TERRA_IN", "200")), int(os.getenv("PRICE_TERRA_OUT", "1200"))),
    "gpt-5.6-luna": (int(os.getenv("PRICE_LUNA_IN", "20")), int(os.getenv("PRICE_LUNA_OUT", "120"))),
}

#: Charged for a model whose price is not listed. Deliberately the most expensive tier:
#: an unknown model must never be cheaper to run than a known one, or misconfiguration
#: becomes a way to spend without the meter noticing.
UNKNOWN_PRICE = (400, 2000)

#: Per-run and per-day ceilings. The run cap is the one an agent can hit; the day cap is
#: what stops a loop somewhere else from draining the account overnight.
RUN_CAP_CENTS = int(os.getenv("AGENT_RUN_CAP_CENTS", "1000"))
DAY_CAP_CENTS = int(os.getenv("AGENT_DAY_CAP_CENTS", "7500"))

#: Assumed worst case for one call before it is made, used only for the pre-flight
#: check. Replaced by reported usage immediately afterwards.
ESTIMATED_INPUT_TOKENS = 20_000
ESTIMATED_OUTPUT_TOKENS = 2_048


class BudgetExceeded(RuntimeError):
    """A cap would be breached. The caller stops and reports; it does not degrade."""


def price_of(model: str) -> tuple[int, int]:
    return PRICES.get(model, UNKNOWN_PRICE)


def cost_cents(model: str, input_tokens: int, output_tokens: int) -> int:
    """Exact cost in cents, rounded up. Never returns less than was spent."""
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Token counts cannot be negative")
    rate_in, rate_out = price_of(model)
    micro = input_tokens * rate_in + output_tokens * rate_out
    return -(-micro // 1_000_000)  # ceiling division on integers


def estimate_cents(model: str) -> int:
    """Worst case for one call, for the check made before spending anything."""
    return cost_cents(model, ESTIMATED_INPUT_TOKENS, ESTIMATED_OUTPUT_TOKENS)


@dataclass
class Meter:
    """One run's spend, shared by every agent inside it.

    A task-level cap and a run-level cap both apply: an agent cannot exceed its own
    allowance, and the agents together cannot exceed the run's, however the work is
    divided between them.
    """

    run_cap_cents: int = RUN_CAP_CENTS
    spent_cents: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    #: agent id -> what that agent has spent inside this run.
    by_agent: dict[str, int] = field(default_factory=dict)
    #: agent id -> model calls and tool calls it has made.
    calls_by_agent: dict[str, int] = field(default_factory=dict)
    tools_by_agent: dict[str, int] = field(default_factory=dict)

    @property
    def remaining_cents(self) -> int:
        return max(0, self.run_cap_cents - self.spent_cents)

    def check_model_call(self, agent_id: str, model: str, budget) -> None:
        """Refuse a call whose worst case would breach a cap, before it is made."""
        if self.calls_by_agent.get(agent_id, 0) >= budget.model_calls:
            raise BudgetExceeded(
                f"{agent_id} has used its {budget.model_calls} model call(s) for this task.")
        estimate = estimate_cents(model)
        if self.by_agent.get(agent_id, 0) + estimate > budget.usd_cents:
            raise BudgetExceeded(
                f"{agent_id} would exceed its task budget of {budget.usd_cents} cent(s).")
        if self.spent_cents + estimate > self.run_cap_cents:
            raise BudgetExceeded(
                f"This run would exceed its cap of {self.run_cap_cents} cent(s). "
                "Nothing further was requested.")

    def charge_model_call(self, agent_id: str, model: str, input_tokens: int, output_tokens: int) -> int:
        """Record what a completed call actually cost, and return it."""
        spent = cost_cents(model, input_tokens, output_tokens)
        self.spent_cents += spent
        self.model_calls += 1
        self.by_agent[agent_id] = self.by_agent.get(agent_id, 0) + spent
        self.calls_by_agent[agent_id] = self.calls_by_agent.get(agent_id, 0) + 1
        return spent

    def charge_tool_call(self, agent_id: str, budget) -> None:
        """Evidence reads cost no money but are still bounded, because an agent that
        reads without concluding is a loop rather than a cheap agent."""
        used = self.tools_by_agent.get(agent_id, 0)
        if used >= budget.tool_calls:
            raise BudgetExceeded(
                f"{agent_id} has used its {budget.tool_calls} evidence call(s) for this task.")
        self.tools_by_agent[agent_id] = used + 1
        self.tool_calls += 1

    def snapshot(self) -> dict:
        return {
            "spent_cents": self.spent_cents, "cap_cents": self.run_cap_cents,
            "remaining_cents": self.remaining_cents,
            "model_calls": self.model_calls, "tool_calls": self.tool_calls,
            "by_agent": dict(sorted(self.by_agent.items())),
        }


def spent_today(connection, ws: str) -> int:
    """What this workspace has spent since midnight UTC, from the decision trail.

    Read from `agent_decisions` rather than a counter, so a restart cannot reset it and
    the day's spend is always reconcilable against the work it paid for.
    """
    row = connection.execute(
        "SELECT COALESCE(SUM(cost_cents), 0) FROM agent_decisions "
        "WHERE ws=? AND created_at >= date('now') || 'T00:00:00'", (ws,)).fetchone()
    return int(row[0] or 0)


def check_day_cap(connection, ws: str, about_to_spend: int = 0) -> None:
    already = spent_today(connection, ws)
    if already + about_to_spend > DAY_CAP_CENTS:
        raise BudgetExceeded(
            f"This workspace has spent {already} cent(s) today, against a daily cap of "
            f"{DAY_CAP_CENTS}. Raise AGENT_DAY_CAP_CENTS or wait until tomorrow.")
