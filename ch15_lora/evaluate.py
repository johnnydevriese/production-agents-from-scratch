"""Stage 4 — the head-to-head, scored on the PATH, on a time-held-out slice.

This is where path-vs-answer is sharpest: we score the *route* — a label — against
the human-confirmed gold label, never the downstream answer. A flawless answer
from the wrong specialist is the Chapter 13 failure, and no answer-quality score
detects it.

The two routers run the *identical* held-out cases, so the comparison is paired —
which is exactly what McNemar's test (Chapter 21) needs to separate a real
difference from noise. A one-point macro-F1 gap is almost always noise; gate the
swap on the test, not the gap in means.

Pure code over recorded `RoutingResult`s. Reuses Chapter 14's per-class metrics
and Chapter 21's paired test; runs no model and spends nothing.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from autopilot import Specialist
from ch14_routing_eval.routing_eval import RoutingResult, precision, recall
from ch21_stats.compare import paired_eval_test


def accuracy(results: Sequence[RoutingResult]) -> float:
    """Aggregate correct-rate. Compare against the majority baseline (mine.py): a
    high accuracy that never beats the do-nothing floor is no router at all."""
    if not results:
        raise ValueError("cannot compute accuracy over zero results")
    return sum(result.correct for result in results) / len(results)


def f1(results: Sequence[RoutingResult], label: Specialist) -> float:
    """Harmonic mean of precision and recall for one class.

    Returns 0.0 when the class is never predicted *and* always missed — the
    pathological case macro-F1 exists to expose.
    """
    relevant = [r for r in results if r.case.gold == label]
    predicted = [r for r in results if r.predicted == label]
    if not relevant and not predicted:
        raise ValueError(f"no cases touch {label.value}")
    p = precision(results, label) if predicted else 0.0
    r = recall(results, label) if relevant else 0.0
    if p + r == 0.0:
        return 0.0
    return 2 * p * r / (p + r)


def macro_f1(results: Sequence[RoutingResult]) -> float:
    """Per-class F1 averaged with equal weight per class.

    Macro, not micro, on purpose: it refuses to let the dominant class paper over
    a rare one. A router that never predicts `VENDOR_MGMT` posts a high aggregate
    accuracy but a wrecked macro-F1 — the number that should gate the swap.
    """
    labels = [
        label for label in Specialist if any(r.case.gold == label for r in results)
    ]
    if not labels:
        raise ValueError("no gold labels present in results")
    return sum(f1(results, label) for label in labels) / len(labels)


def _paired(
    baseline: Sequence[RoutingResult], candidate: Sequence[RoutingResult]
) -> tuple[int, int]:
    """Count discordant pairs across the *same* cases: (regressions, gains).

    Concordant cases (both right, both wrong) carry no information about which
    router is better — McNemar looks only at the flips.
    """
    if len(baseline) != len(candidate):
        raise ValueError("head-to-head needs the same cases run through both routers")
    regressions = 0
    gains = 0
    for base, cand in zip(baseline, candidate, strict=True):
        if base.case.request != cand.case.request or base.case.gold != cand.case.gold:
            raise ValueError("paired results must be aligned case-for-case")
        if base.correct and not cand.correct:
            regressions += 1
        elif cand.correct and not base.correct:
            gains += 1
    return regressions, gains


class HeadToHead(BaseModel):
    """Two routers on identical held-out cases, scored on the path."""

    baseline_macro_f1: float
    candidate_macro_f1: float
    baseline_ap_recall: float
    candidate_ap_recall: float
    regressions: int  # baseline right, candidate wrong
    gains: int  # candidate right, baseline wrong
    mcnemar_p_value: float

    @property
    def significant(self) -> bool:
        """A real difference at alpha=0.05 — not a one-point gap that is just noise."""
        return self.mcnemar_p_value < 0.05


def head_to_head(
    *, baseline: Sequence[RoutingResult], candidate: Sequence[RoutingResult]
) -> HeadToHead:
    """Compare a candidate router (the LoRA adapter) against a baseline (the LLM
    router) on identical cases. The verdict is the McNemar p-value, not the gap in
    means — and AP recall is reported alongside because a missed AP route leaves a
    duplicate charge live (Ch 13)."""
    regressions, gains = _paired(baseline, candidate)
    # With no flips there is no evidence of a difference: p = 1.0 by definition,
    # and the exact test is degenerate on an all-zero table.
    p_value = (
        paired_eval_test(pass_to_fail=regressions, fail_to_pass=gains)
        if regressions + gains > 0
        else 1.0
    )
    return HeadToHead(
        baseline_macro_f1=macro_f1(baseline),
        candidate_macro_f1=macro_f1(candidate),
        baseline_ap_recall=recall(baseline, Specialist.AP),
        candidate_ap_recall=recall(candidate, Specialist.AP),
        regressions=regressions,
        gains=gains,
        mcnemar_p_value=p_value,
    )
