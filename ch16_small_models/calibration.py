"""Calibration — the reason the cascade's confidence threshold means anything.

A classifier's raw confidence is often miscalibrated: it says 0.99 when it's right
0.90 of the time. For `tau` to *mean* something, "confidence >= 0.90" must actually
correspond to "right >= 90% of the time" — otherwise the threshold is a lie and the
cascade quietly keeps invoices it shouldn't. This module measures that with a
reliability table and the expected calibration error, and reports what a given
`tau` does to a held-out set: how much falls up, and whether the student really is
more accurate on the cases it kept. Pure functions over graded outputs; no spend.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from pydantic import BaseModel, Field


class GradedCoding(BaseModel):
    """A coder's output on a held-out case, graded against the human label."""

    stated_confidence: float = Field(ge=0.0, le=1.0)
    correct: bool


class CalibrationBucket(BaseModel):
    lower: float  # bucket's confidence floor
    upper: float  # bucket's confidence ceiling
    mean_confidence: float  # what the model claimed, on average, in this bucket
    observed_accuracy: float  # what it actually got right
    count: int


def _bucket_index(confidence: float, bins: int) -> int:
    return min(int(confidence * bins), bins - 1)  # clamp 1.0 into the last bucket


def reliability_table(
    graded: Sequence[GradedCoding], *, bins: int = 10
) -> list[CalibrationBucket]:
    """Group outputs into confidence buckets and compare claimed vs observed.

    A perfectly calibrated coder has `mean_confidence == observed_accuracy` in every
    bucket — the points sit on the diagonal.
    """
    if not graded:
        raise ValueError("cannot build a reliability table over zero outputs")
    if bins < 1:
        raise ValueError(f"bins must be >= 1, got {bins}")
    grouped: dict[int, list[GradedCoding]] = defaultdict(list)
    for output in graded:
        grouped[_bucket_index(output.stated_confidence, bins)].append(output)
    width = 1.0 / bins
    return [
        CalibrationBucket(
            lower=index * width,
            upper=(index + 1) * width,
            mean_confidence=sum(m.stated_confidence for m in members) / len(members),
            observed_accuracy=sum(m.correct for m in members) / len(members),
            count=len(members),
        )
        for index, members in sorted(grouped.items())
    ]


def expected_calibration_error(
    graded: Sequence[GradedCoding], *, bins: int = 10
) -> float:
    """Count-weighted average gap between claimed confidence and observed accuracy.

    0.0 is perfect; a large ECE means the threshold cannot be trusted. This is the
    single number that tells you whether `tau` is honest.
    """
    table = reliability_table(graded, bins=bins)
    total = len(graded)
    return sum(
        bucket.count / total * abs(bucket.mean_confidence - bucket.observed_accuracy)
        for bucket in table
    )


def is_calibrated(
    graded: Sequence[GradedCoding], *, tolerance: float = 0.1, bins: int = 10
) -> bool:
    return expected_calibration_error(graded, bins=bins) <= tolerance


class ThresholdReport(BaseModel):
    """What a chosen `tau` does to a held-out set."""

    tau: float
    kept_fraction: float  # conf >= tau: the student owns these (the cheap path)
    fallup_fraction: float  # conf < tau: fall up to the teacher
    accuracy_on_kept: float | None  # None if the student kept nothing
    accuracy_on_fallup: float | None  # None if nothing fell up


def threshold_report(graded: Sequence[GradedCoding], *, tau: float) -> ThresholdReport:
    """Split a held-out set at `tau` and measure both sides.

    A well-calibrated student is markedly more accurate on the cases it *kept* than
    on the ones it *passed up* — that gap is the whole justification for trusting it
    below the line and escalating above it.
    """
    if not graded:
        raise ValueError("cannot report a threshold over zero outputs")
    kept = [output for output in graded if output.stated_confidence >= tau]
    fell_up = [output for output in graded if output.stated_confidence < tau]
    total = len(graded)
    return ThresholdReport(
        tau=tau,
        kept_fraction=len(kept) / total,
        fallup_fraction=len(fell_up) / total,
        accuracy_on_kept=(
            sum(output.correct for output in kept) / len(kept) if kept else None
        ),
        accuracy_on_fallup=(
            sum(output.correct for output in fell_up) / len(fell_up)
            if fell_up
            else None
        ),
    )
