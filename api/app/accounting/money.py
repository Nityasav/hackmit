"""Exact money math. Integer cents only, never floats (spec.md §6).

Owner: Functionality. Invariant IDs refer to ACCOUNTING_CONTROLS.md §2.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
import re


def parse_minor_units(raw: str, unit: str = "major") -> int:
    """Parse uploaded money exactly, including values beyond Decimal's default precision.

    Bound amounts to the safe integer range shared with the TypeScript contract.
    """
    if len(raw) > 80 or not re.fullmatch(r"-?\d+(?:\.\d+)?", raw):
        raise ValueError("Use an exact number without currency symbols or grouping separators")
    if unit not in {"major", "minor"}:
        raise ValueError("Amount unit must be major or minor")
    try:
        with localcontext() as context:
            context.prec = max(32, len(raw) + 4)
            amount = Decimal(raw) * (100 if unit == "major" else 1)
            if not amount.is_finite() or amount != amount.to_integral_value() or abs(amount) > 9_000_000_000_000:
                raise ValueError("Unsupported monetary precision or amount")
            return int(amount)
    except InvalidOperation:
        raise ValueError("Invalid amount") from None


class InvariantError(ValueError):
    """Raised when a ledger invariant (L01–L13) fails."""


@dataclass(frozen=True)
class JournalLine:
    account: str
    fund: str
    debit_cents: int = 0
    credit_cents: int = 0


def split_amount(total_cents: int, weights: list[int]) -> list[int]:
    """Split an amount by weights using largest remainder (L11: parts sum to the total).

    >>> split_amount(1_000_000, [60, 40])
    [600000, 400000]
    >>> sum(split_amount(1_000_01, [1, 1, 1]))
    100001
    """
    if not weights or any(w < 0 for w in weights):
        raise InvariantError("weights must be non-empty and non-negative")
    weight_total = sum(weights)
    if weight_total == 0:
        raise InvariantError("weights must not sum to zero")

    sign = -1 if total_cents < 0 else 1
    amount = abs(total_cents)

    exact = [amount * w for w in weights]
    parts = [e // weight_total for e in exact]
    remainders = [(e % weight_total, i) for i, e in enumerate(exact)]

    shortfall = amount - sum(parts)
    # Largest remainder first; ties break on index so the result is deterministic.
    for _, i in sorted(remainders, key=lambda r: (-r[0], r[1]))[:shortfall]:
        parts[i] += 1

    if sum(parts) != amount:
        raise InvariantError("L11: allocation parts do not sum to the original amount")
    return [p * sign for p in parts]


def assert_balanced(lines: list[JournalLine]) -> None:
    """L01: total debits must equal total credits, in cents."""
    debits = sum(line.debit_cents for line in lines)
    credits = sum(line.credit_cents for line in lines)
    if debits != credits:
        raise InvariantError(f"L01: debits {debits} != credits {credits}")
    for line in lines:
        if line.debit_cents < 0 or line.credit_cents < 0:
            raise InvariantError("L02: a line may not have a negative side")
        if line.debit_cents and line.credit_cents:
            raise InvariantError("L02: a line must have exactly one non-zero side")


def cash_delta(lines: list[JournalLine], cash_accounts: set[str] | None = None) -> int:
    """Net cash movement of a journal. A pure reclassification must return 0 (AC-06)."""
    cash_accounts = cash_accounts or {"Cash"}
    return sum(
        line.debit_cents - line.credit_cents for line in lines if line.account in cash_accounts
    )


def reclassification(
    account: str, from_fund: str, to_fund: str, amount_cents: int
) -> list[JournalLine]:
    """Move spend between funds without touching cash or the expense total."""
    lines = [
        JournalLine(account=account, fund=to_fund, debit_cents=amount_cents),
        JournalLine(account=account, fund=from_fund, credit_cents=amount_cents),
    ]
    assert_balanced(lines)
    return lines


def money(cents: int) -> str:
    return f"{'−' if cents < 0 else ''}${abs(cents) / 100:,.2f}"
