"""Wilson score intervals — honest error bars on a pass rate.

A 26-case suite that scores 24/26 is not "92%"; it's 92% ± about ten points. The
Wilson interval is well-behaved at small n and near 0/1, where the textbook
normal (Wald) interval falls outside [0, 1] and gives a width-zero lie at 26/26.
"""

from __future__ import annotations

from statsmodels.stats.proportion import proportion_confint


def wilson_interval(
    passes: int, n: int, *, confidence: float = 0.95
) -> tuple[float, float]:
    """95% Wilson score interval for a pass rate. Well-behaved at small n and near 0/1."""
    alpha = 1.0 - confidence
    low, high = proportion_confint(passes, n, alpha=alpha, method="wilson")
    return (float(low), float(high))  # float() pins statsmodels' untyped return
