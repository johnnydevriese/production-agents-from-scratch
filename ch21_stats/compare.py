"""McNemar's paired test — comparing two eval runs on the *same* cases.

The two versions ran the identical suite, so the measurements are paired. McNemar
looks only at the cases that *flipped* (pass→fail and fail→pass); the cases that
passed or failed in both carry zero information about which version is better.
One net flip is never significant — you need several consistent ones.
"""

from __future__ import annotations

from typing import Any

from statsmodels.stats.contingency_tables import mcnemar


def paired_eval_test(*, pass_to_fail: int, fail_to_pass: int) -> float:
    """McNemar p-value for two versions run on the same cases. Returns the p-value."""
    table = [
        [0, pass_to_fail],  # [both-pass placeholder, b: pass→fail]
        [fail_to_pass, 0],  # [c: fail→pass, both-fail placeholder]
    ]
    result: Any = mcnemar(table, exact=True)  # statsmodels' Bunch is dynamically typed
    return float(result.pvalue)
