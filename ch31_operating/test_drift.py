"""Drift detection against a reference window.

These pin: a small wiggle off the reference window is not drift (overlapping
intervals); a large, sustained rise is; and the leading-indicator table names what a
rise reveals. Reuses Chapter 21's Wilson interval; pure, no spend.
"""

from __future__ import annotations

from .drift import LEADING_INDICATORS, is_drifting


def test_a_small_wiggle_is_not_drift() -> None:
    # 3% at release, 4% now, on modest volume — within noise, not a signal.
    assert not is_drifting(reference_bad=30, reference_n=1000, live_bad=40, live_n=1000)


def test_a_large_sustained_rise_is_drift() -> None:
    # 3% at release, 9% now, on real volume — the world moved under a pinned model.
    assert is_drifting(reference_bad=30, reference_n=1000, live_bad=90, live_n=1000)


def test_an_improvement_is_never_flagged_as_drift() -> None:
    # The exception rate fell; drift is one-directional (worse), so this is quiet.
    assert not is_drifting(reference_bad=90, reference_n=1000, live_bad=20, live_n=1000)


def test_the_leading_indicators_explain_what_a_rise_reveals() -> None:
    assert "approval_override_rate" in LEADING_INDICATORS
    # Each indicator says what *moved*, not merely that something did.
    assert all(meaning for meaning in LEADING_INDICATORS.values())
