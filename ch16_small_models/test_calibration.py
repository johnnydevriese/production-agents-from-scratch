"""Calibration is what makes the threshold mean something.

These pin: a calibrated coder has near-zero ECE; an overconfident one is caught; the
reliability table buckets by confidence; and a `tau` split shows the student far
more accurate on what it kept than on what it passed up — the whole justification
for trusting it below the line. Pure, no spend.
"""

from __future__ import annotations

import pytest

from .calibration import (
    GradedCoding,
    expected_calibration_error,
    is_calibrated,
    reliability_table,
    threshold_report,
)


def _graded(confidence: float, *, correct: bool, n: int) -> list[GradedCoding]:
    return [
        GradedCoding(stated_confidence=confidence, correct=correct) for _ in range(n)
    ]


def test_a_calibrated_coder_has_near_zero_calibration_error() -> None:
    # Claims 0.9 and is right 90% of the time; claims 0.5 and is right half the time.
    graded = (
        _graded(0.9, correct=True, n=90)
        + _graded(0.9, correct=False, n=10)
        + _graded(0.5, correct=True, n=50)
        + _graded(0.5, correct=False, n=50)
    )
    assert expected_calibration_error(graded) == pytest.approx(0.0, abs=1e-9)
    assert is_calibrated(graded)


def test_an_overconfident_coder_is_caught() -> None:
    # Claims 0.99 but is right only half the time — the threshold would be a lie.
    graded = _graded(0.99, correct=True, n=50) + _graded(0.99, correct=False, n=50)
    assert expected_calibration_error(graded) == pytest.approx(0.49, abs=1e-6)
    assert not is_calibrated(graded)


def test_the_reliability_table_buckets_by_confidence() -> None:
    graded = _graded(0.15, correct=False, n=4) + _graded(0.95, correct=True, n=6)
    table = reliability_table(graded, bins=10)

    assert [bucket.count for bucket in table] == [4, 6]  # one low bucket, one high
    assert table[0].observed_accuracy == 0.0
    assert table[1].observed_accuracy == 1.0


def test_the_threshold_splits_kept_from_fallup_and_the_kept_side_is_more_accurate() -> (
    None
):
    # Confident-and-mostly-right vs unsure-and-mostly-wrong — a well-calibrated student.
    graded = (
        _graded(0.95, correct=True, n=90)
        + _graded(0.95, correct=False, n=10)
        + _graded(0.40, correct=True, n=20)
        + _graded(0.40, correct=False, n=80)
    )
    report = threshold_report(graded, tau=0.90)

    assert report.kept_fraction == pytest.approx(0.5)
    assert report.fallup_fraction == pytest.approx(0.5)
    assert report.accuracy_on_kept is not None
    assert report.accuracy_on_fallup is not None
    assert report.accuracy_on_kept == pytest.approx(0.9)
    assert report.accuracy_on_fallup == pytest.approx(0.2)
    assert report.accuracy_on_kept > report.accuracy_on_fallup  # the justification


def test_the_threshold_report_handles_an_empty_side() -> None:
    graded = _graded(0.95, correct=True, n=10)  # everything is confident
    report = threshold_report(graded, tau=0.90)
    assert report.kept_fraction == 1.0
    assert report.fallup_fraction == 0.0
    assert report.accuracy_on_fallup is None  # nothing fell up


def test_calibration_over_zero_outputs_raises() -> None:
    with pytest.raises(ValueError, match="zero outputs"):
        expected_calibration_error([])
