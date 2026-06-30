"""The canary gates, point-estimate and statistically honest.

These pin: a clean canary promotes; a path or money-movement violation rolls back at
zero tolerance; an answer-quality wobble within tolerance is allowed; and the
small-sample version only calls a regression real when the Wilson intervals (Ch 21)
do not overlap — so you don't roll back on noise. Pure, no spend.
"""

from __future__ import annotations

from .canary import GATES, canary_breaches, significant_breaches

_CLEAN = {
    "path_violation_rate": 0.0,
    "approval_override_rate": 0.05,
    "judge_score_p50_drop": 0.0,
    "schedule_payment_error_rate": 0.0,
}


def test_a_clean_canary_promotes() -> None:
    assert canary_breaches(canary=_CLEAN, control=_CLEAN) == []


def test_a_single_path_violation_rolls_back_at_zero_tolerance() -> None:
    canary = {**_CLEAN, "path_violation_rate": 0.001}  # one skipped check_budget
    assert canary_breaches(canary=canary, control=_CLEAN) == ["path_violation_rate"]


def test_a_money_movement_error_rolls_back() -> None:
    canary = {**_CLEAN, "schedule_payment_error_rate": 0.01}
    assert canary_breaches(canary=canary, control=_CLEAN) == [
        "schedule_payment_error_rate"
    ]


def test_an_override_wobble_within_tolerance_is_allowed() -> None:
    # 2pp worse is the documented tolerance; just under it must not roll back.
    canary = {
        **_CLEAN,
        "approval_override_rate": _CLEAN["approval_override_rate"] + 0.019,
    }
    assert canary_breaches(canary=canary, control=_CLEAN) == []


def test_an_override_regression_beyond_tolerance_rolls_back() -> None:
    canary = {
        **_CLEAN,
        "approval_override_rate": _CLEAN["approval_override_rate"] + 0.05,
    }
    assert "approval_override_rate" in canary_breaches(canary=canary, control=_CLEAN)


def test_the_path_and_money_gates_are_zero_tolerance() -> None:
    assert GATES["path_violation_rate"] == 0.0
    assert GATES["schedule_payment_error_rate"] == 0.0


def test_a_small_sample_difference_is_not_significant() -> None:
    # 1/100 vs 0/100 looks worse, but the intervals overlap — rolling back here is
    # rolling back on noise.
    assert not significant_breaches(
        canary_bad=1, canary_n=100, control_bad=0, control_n=100
    )


def test_a_large_consistent_difference_is_significant() -> None:
    # 30/100 vs 2/100 on real volume — the intervals separate, a real regression.
    assert significant_breaches(
        canary_bad=30, canary_n=100, control_bad=2, control_n=100
    )
