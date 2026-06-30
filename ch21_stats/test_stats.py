"""Tests that also pin the exact figures Chapter 21 cites. Pure, offline."""

from __future__ import annotations

import pytest

from .compare import paired_eval_test
from .intervals import wilson_interval


def test_wilson_band_on_24_of_26_is_about_plus_minus_ten_points() -> None:
    low, high = wilson_interval(24, 26)
    assert low == pytest.approx(0.760, abs=0.01)
    assert high == pytest.approx(0.979, abs=0.01)


def test_wilson_does_not_collapse_to_width_zero_at_the_boundary() -> None:
    # The whole reason to prefer Wilson over Wald: 26/26 is NOT [1.0, 1.0].
    low, high = wilson_interval(26, 26)
    assert high == pytest.approx(1.0, abs=1e-9)
    assert low < 0.95


def test_one_net_flip_proves_nothing() -> None:
    # The "24/26 → 25/26" case: a single fail→pass flip.
    p = paired_eval_test(pass_to_fail=0, fail_to_pass=1)
    assert p > 0.9


def test_five_fixes_one_break_still_not_significant_at_small_n() -> None:
    p = paired_eval_test(pass_to_fail=1, fail_to_pass=5)
    assert p == pytest.approx(0.219, abs=0.01)
