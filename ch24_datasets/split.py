"""Dev / golden split — and the wall you guard like a credential.

If you tune against the same cases you report the metric on, you are doing
gradient descent by hand on the eval set: the number stops estimating production
and starts estimating how well you memorized your own quiz. The defense is a
split — iterate on **dev**, report on a sealed **golden** set kept out-of-sample.
The dev/golden gap *is* your overfitting, measured.

Membership is assigned by a stable hash of the case id, so a case never drifts
across the wall between runs (Python's salted `hash()` would). Two integrity
guards make the wall enforceable, not just aspirational:

* `assert_no_leakage` — a case in both halves is a breached wall.
* `assert_golden_eligible` — a freshly MINED case lives in dev until it has been
  reviewed and reclassified; promoting production's current behavior straight into
  the honest number is leakage by another name.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from .cases import EvalCase, Origin


class DatasetError(Exception):
    """Base for dataset-integrity violations."""


class LeakageError(DatasetError):
    """A case appears in both dev and golden — the wall is breached."""


class PrematurePromotionError(DatasetError):
    """A freshly MINED case was routed to golden before review."""


def _bucket(case_id: str) -> int:
    """A stable 0–99 bucket: deterministic across processes, unlike `hash()`."""
    digest = hashlib.sha256(case_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % 100


def split_dev_golden(
    cases: Sequence[EvalCase], *, golden_fraction: float = 0.30
) -> tuple[list[EvalCase], list[EvalCase]]:
    """Partition into (dev, golden). Stable by id, so a case keeps its side."""
    if not 0.0 < golden_fraction < 1.0:
        raise ValueError("golden_fraction must be in (0, 1)")
    cutoff = round(golden_fraction * 100)
    dev: list[EvalCase] = []
    golden: list[EvalCase] = []
    for case in cases:
        (golden if _bucket(case.id) < cutoff else dev).append(case)
    return dev, golden


def assert_no_leakage(dev: Sequence[EvalCase], golden: Sequence[EvalCase]) -> None:
    overlap = {c.id for c in dev} & {c.id for c in golden}
    if overlap:
        raise LeakageError(f"cases in both dev and golden: {sorted(overlap)}")


def assert_golden_eligible(case: EvalCase) -> None:
    if case.origin is Origin.MINED:
        raise PrematurePromotionError(
            f"{case.id!r} is freshly MINED — it stays in dev until reviewed and "
            "reclassified (a stabilized mined case becomes a REGRESSION case)."
        )
