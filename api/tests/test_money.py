import pytest

from app.accounting.money import (
    InvariantError,
    assert_balanced,
    cash_delta,
    money,
    reclassification,
    split_amount,
)


def test_sixty_forty_split_of_ten_thousand():
    assert split_amount(1_000_000, [60, 40]) == [600_000, 400_000]


def test_eighty_twenty_split_gives_two_thousand_back():
    award, general = split_amount(1_000_000, [80, 20])
    assert general == 200_000
    assert award + general == 1_000_000


@pytest.mark.parametrize("total", [1, 2, 100_001, 999_999, 33_333])
@pytest.mark.parametrize("weights", [[1, 1, 1], [60, 40], [50, 30, 20], [7, 11, 13]])
def test_parts_always_sum_to_total(total, weights):
    assert sum(split_amount(total, weights)) == total


def test_negative_amounts_keep_their_sign():
    assert split_amount(-1_000_000, [60, 40]) == [-600_000, -400_000]


def test_zero_weights_rejected():
    with pytest.raises(InvariantError):
        split_amount(100, [0, 0])


def test_reclassification_balances_and_moves_no_cash():
    lines = reclassification("Salary expense", "Student-support award", "General operations", 400_000)
    assert_balanced(lines)
    assert cash_delta(lines) == 0


def test_unbalanced_journal_is_rejected():
    from app.accounting.money import JournalLine

    with pytest.raises(InvariantError):
        assert_balanced([JournalLine("Salary expense", "General", debit_cents=400_000)])


def test_money_formatting():
    assert money(400_000) == "$4,000.00"
    assert money(-1) == "−$0.01"


def test_zero_sided_journal_line_is_rejected():
    from app.accounting.money import JournalLine

    with pytest.raises(InvariantError):
        assert_balanced([JournalLine("Cash", "General")])


def test_money_formatting_does_not_lose_cents_to_float():
    assert money(9_007_199_254_740_993) == "$90,071,992,547,409.93"


def test_seeded_allocation_reference_invariants():
    import random
    from fractions import Fraction

    rng = random.Random(20260919)
    for _ in range(1000):
        total = rng.randrange(-9_000_000_000_000, 9_000_000_000_000)
        weights = [rng.randrange(1, 1000) for _ in range(rng.randrange(1, 20))]
        parts = split_amount(total, weights)
        assert sum(parts) == total
        for part, weight in zip(parts, weights):
            exact = Fraction(total * weight, sum(weights))
            assert abs(Fraction(part) - exact) < 1
            assert part == 0 or (part > 0) == (total > 0)
