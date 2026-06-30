"""Discipline 3 — roll out behind a canary that gates on evals, not vibes.

The canary's superpower is the control group running *in parallel on the same
distribution*: drift and seasonality hit both arms equally, so a difference between
them is attributable to the release, not to "Tuesdays are weird." Every gate has an
automated threshold that can roll back without a human.

Two gates are pinned at `0.0` on purpose. Path violations and money-movement errors
are the **path**, not the **answer**, and the path of a money-moving agent gets zero
tolerance — a canary that pays one wrong invoice has already failed, however fluent
its summaries got.

`canary_breaches` compares point estimates (the chapter's listing). `significant_breaches`
is the production discipline the chapter flags: a 1% slice is a small sample, so a
breach must clear a Wilson interval (Chapter 21) before you trust it — otherwise you
roll back on noise and ship on luck.
"""

from __future__ import annotations

import logging

from ch21_stats.intervals import wilson_interval

logger = logging.getLogger(__name__)

# Data-driven, not an if/elif chain: gate name -> max tolerated regression vs control.
# These are the SAME online metrics Chapter 23 already computes on every trace.
GATES: dict[str, float] = {
    "path_violation_rate": 0.0,  # ZERO tolerance: a skipped check_budget is never ok
    "approval_override_rate": 0.02,  # canary may be at most 2pp worse than control
    "judge_score_p50_drop": 0.3,  # answer-quality drop the judge (Ch 22) tolerates
    "schedule_payment_error_rate": 0.0,  # money movement: zero tolerance
}


def canary_breaches(
    *, canary: dict[str, float], control: dict[str, float]
) -> list[str]:
    """Gates the canary arm fails vs. the control arm. Empty ⇒ promote. Point
    estimates only — see `significant_breaches` for the small-sample-honest version."""
    breached = [
        gate
        for gate, tolerance in GATES.items()
        if canary[gate] - control[gate] > tolerance
    ]
    if breached:
        logger.error("canary breached gates, rolling back: %s", breached)
    return breached


def significant_breaches(
    *,
    canary_bad: int,
    canary_n: int,
    control_bad: int,
    control_n: int,
    confidence: float = 0.95,
) -> bool:
    """Is the canary's failure rate *significantly* worse than control's?

    A 1% slice is a small sample, so we wrap each arm's bad-event rate in a Wilson
    interval (Chapter 21) and only call it a real regression when the intervals do not
    overlap — the canary's lower bound sits above the control's upper bound. This is
    what keeps you from rolling back on run-to-run noise.
    """
    canary_low, _canary_high = wilson_interval(
        canary_bad, canary_n, confidence=confidence
    )
    _control_low, control_high = wilson_interval(
        control_bad, control_n, confidence=confidence
    )
    return canary_low > control_high
