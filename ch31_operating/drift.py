"""Discipline 4a — detect drift before it pages you.

Drift is invisible per-trace — there is no single bad run to find, which is exactly
why it survives the on-call playbook. It shows only in *aggregate, over time*, in the
leading indicators Chapter 23 already computes. The honest way to detect it is a
**reference window** — the distribution when the current release passed its evals —
compared against the live window.

`is_drifting` makes "rising" a statistical claim, not a vibe: it reuses Chapter 21's
Wilson interval and only fires when the live window's bad-event rate is *clearly*
above the reference window's — the intervals do not overlap. A `match_to_po`
exception rate that was 3% at release and is 7% now, on enough volume, is the world
telling you your fixtures are going stale (the problem Chapter 24 exists to outrun).
"""

from __future__ import annotations

from ch21_stats.intervals import wilson_interval

# The leading indicators to trend against a reference window (Chapter 23). The value
# is what a rise reveals — what moved, not just that something did.
LEADING_INDICATORS: dict[str, str] = {
    "approval_override_rate": "the agent's proposals are getting worse",
    "match_to_po_exception_rate": "invoice/PO formats are shifting upstream",
    "judge_score_p50": "answer quality is eroding (model or distribution)",
    "new_bank_account_filter_rate": "the vendor base is changing — or under attack",
    "tool_arg_distribution_shift": "a new vendor segment on an untested path",
}


def is_drifting(
    *,
    reference_bad: int,
    reference_n: int,
    live_bad: int,
    live_n: int,
    confidence: float = 0.95,
) -> bool:
    """Has a leading indicator drifted *significantly* above its reference window?

    True only when the live window's bad-rate Wilson interval sits entirely above the
    reference window's — i.e. the rise clears run-to-run noise. Comparing point rates
    alone would fire on every wiggle; the interval is what makes the alarm trustworthy.
    """
    _ref_low, ref_high = wilson_interval(
        reference_bad, reference_n, confidence=confidence
    )
    live_low, _live_high = wilson_interval(live_bad, live_n, confidence=confidence)
    return live_low > ref_high
