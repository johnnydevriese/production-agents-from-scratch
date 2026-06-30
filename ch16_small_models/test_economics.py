"""Volume is the whole justification — the break-even is a number, not a vibe.

These pin: frontier-only scales linearly; the cascade wins at high volume and loses
below break-even; and `break_even_volume` is the crossover. A cascade that never
trusts the student can't break even. Pure arithmetic, no spend.
"""

from __future__ import annotations

import pytest

from .economics import (
    CostModel,
    break_even_volume,
    monthly_cost_cascade,
    monthly_cost_frontier_only,
)


def _cost() -> CostModel:
    # $0.02 per frontier call, $1,000/mo to serve the student, 5% falls up.
    return CostModel(
        frontier_cost_per_call=0.02,
        student_monthly_serving_cost=1000.0,
        fallup_rate=0.05,
    )


def test_frontier_only_scales_linearly_with_volume() -> None:
    cost = _cost()
    assert monthly_cost_frontier_only(cost, invoices_per_month=200) == pytest.approx(
        2 * monthly_cost_frontier_only(cost, invoices_per_month=100)
    )


def test_the_cascade_wins_at_high_volume() -> None:
    cost = _cost()
    high = 100_000
    assert monthly_cost_cascade(
        cost, invoices_per_month=high
    ) < monthly_cost_frontier_only(cost, invoices_per_month=high)


def test_frontier_only_wins_far_below_break_even() -> None:
    cost = _cost()
    low = 100
    assert monthly_cost_frontier_only(
        cost, invoices_per_month=low
    ) < monthly_cost_cascade(cost, invoices_per_month=low)


def test_break_even_volume_is_the_crossover() -> None:
    cost = _cost()
    n = break_even_volume(cost)
    assert n == 52632  # ceil(1000 / (0.02 * 0.95))

    # At break-even the cascade is (just) cheaper; one invoice below, it isn't.
    assert monthly_cost_cascade(
        cost, invoices_per_month=n
    ) <= monthly_cost_frontier_only(cost, invoices_per_month=n)
    assert monthly_cost_cascade(
        cost, invoices_per_month=n - 1
    ) > monthly_cost_frontier_only(cost, invoices_per_month=n - 1)


def test_a_cascade_that_never_trusts_the_student_cannot_break_even() -> None:
    never = CostModel(
        frontier_cost_per_call=0.02,
        student_monthly_serving_cost=1000.0,
        fallup_rate=1.0,
    )
    with pytest.raises(ValueError, match="never break even"):
        break_even_volume(never)
