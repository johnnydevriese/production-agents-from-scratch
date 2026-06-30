"""ch20 — tool precision / recall / F1 as pure set math.

No model, no span tree: feed two lists of tool names (what it should have called,
what it did) and assert the confusion counts. The double-pay is a *precision*
failure on `schedule_payment`; a skipped control is a *recall* failure; a reordering
is a false-positive *transition* that a plain tool-set comparison would miss.
"""

from __future__ import annotations

import pytest

from .metrics import aggregate, f1, per_case_counts, precision, recall

_HAPPY = ["check_budget", "request_approval", "schedule_payment", "post_journal_entry"]


def test_perfect_path_scores_one() -> None:
    counts = per_case_counts(expected=_HAPPY, actual=_HAPPY)
    assert precision(counts) == 1.0
    assert recall(counts) == 1.0
    assert f1(counts) == 1.0
    assert counts.step_efficiency == 1.0


def test_double_pay_is_a_precision_failure() -> None:
    # The motivating bug: paid twice. The tool *set* is unchanged, but the extra
    # call drags step_efficiency down and the duplicate shows in tool_call_count.
    actual = ["check_budget", "schedule_payment", "schedule_payment"]
    counts = per_case_counts(expected=_HAPPY, actual=actual)
    assert counts.tool_call_count == 3
    assert counts.step_efficiency < 1.0  # a wasted (dangerous) call
    # It skipped approval and the GL entry -> recall drops.
    assert recall(counts) < 1.0


def test_spurious_tool_lands_in_false_positives() -> None:
    actual = [*_HAPPY, "get_vendor"]  # called a tool it didn't need
    counts = per_case_counts(expected=_HAPPY, actual=actual)
    assert counts.tool_fp == 1
    assert precision(counts) < 1.0
    assert recall(counts) == 1.0  # still called everything required


def test_skipped_control_lands_in_false_negatives() -> None:
    actual = ["request_approval", "schedule_payment", "post_journal_entry"]
    counts = per_case_counts(expected=_HAPPY, actual=actual)
    assert counts.tool_fn == 1  # skipped check_budget
    assert recall(counts) < 1.0
    assert precision(counts) == 1.0


def test_reordering_is_a_false_positive_transition() -> None:
    # Same tool set, wrong order: pay before approval. The tool-set metrics are
    # blind to it; the transition counts catch it.
    reordered = [
        "check_budget",
        "schedule_payment",
        "request_approval",
        "post_journal_entry",
    ]
    counts = per_case_counts(expected=_HAPPY, actual=reordered)
    assert counts.tool_tp == 4 and counts.tool_fp == 0  # set is identical
    assert counts.transition_fp > 0  # but the ordering broke


def test_aggregate_sums_counts_across_cases() -> None:
    a = per_case_counts(expected=_HAPPY, actual=_HAPPY)
    b = per_case_counts(expected=_HAPPY, actual=["check_budget"])
    total = aggregate([a, b])
    assert total.tool_tp == a.tool_tp + b.tool_tp
    assert total.tool_call_count == a.tool_call_count + b.tool_call_count


def test_precision_raises_when_nothing_was_called() -> None:
    counts = per_case_counts(expected=_HAPPY, actual=[])
    with pytest.raises(ValueError, match="precision undefined"):
        precision(counts)
