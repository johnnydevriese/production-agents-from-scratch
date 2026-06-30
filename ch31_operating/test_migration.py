"""Model migration as a behavioral diff over the frozen suite.

These pin: a money-path case flipping pass→fail is an instant stop, however strong
the rest looks; a migration with more gains than regressions is safe; a significantly
worse one is not; and the runs must cover the identical suite (the fixed yardstick).
Reuses Chapter 21's McNemar; pure, no spend.
"""

from __future__ import annotations

from collections.abc import Collection

import pytest

from ch21_stats.compare import paired_eval_test

from .migration import CaseOutcome, migration_diff


def _suite(
    passed: dict[str, bool], *, money: Collection[str] = ()
) -> list[CaseOutcome]:
    return [
        CaseOutcome(name=name, passed=ok, is_money_path=name in money)
        for name, ok in passed.items()
    ]


def test_a_money_path_regression_is_an_instant_stop() -> None:
    money = {"pays_matched_invoice_once"}
    incumbent = _suite(
        {"pays_matched_invoice_once": True, "summary_reads_well": False}, money=money
    )
    # The candidate gains the quality case but loses the money-path one.
    candidate = _suite(
        {"pays_matched_invoice_once": False, "summary_reads_well": True}, money=money
    )
    diff = migration_diff(incumbent=incumbent, candidate=candidate)
    assert diff.money_path_regressions == ["pays_matched_invoice_once"]
    assert not diff.safe_to_migrate  # no benefit of the doubt on money movement


def test_a_clean_improvement_is_safe_to_migrate() -> None:
    incumbent = _suite({f"c{i}": (i < 6) for i in range(12)})
    candidate = _suite({f"c{i}": (i < 10) for i in range(12)})  # four cases recovered
    diff = migration_diff(incumbent=incumbent, candidate=candidate)
    assert diff.gains and not diff.regressions
    assert diff.safe_to_migrate


def test_a_significantly_worse_migration_is_not_a_migration() -> None:
    # Ten cases regress, none gain — McNemar says real, so it must not ship.
    incumbent = _suite({f"c{i}": True for i in range(12)})
    candidate = _suite({f"c{i}": (i >= 10) for i in range(12)})  # c0..c9 flip to fail
    diff = migration_diff(incumbent=incumbent, candidate=candidate)
    assert diff.regressions and not diff.gains
    assert diff.significant
    assert not diff.safe_to_migrate


def test_no_flips_means_no_test_and_a_clean_migration() -> None:
    suite = _suite({f"c{i}": True for i in range(5)})
    diff = migration_diff(incumbent=suite, candidate=suite)
    assert diff.regressions == [] and diff.gains == []
    assert diff.mcnemar_p_value == 1.0  # nothing flipped, nothing to test
    assert diff.safe_to_migrate


def test_the_p_value_matches_chapter_21s_paired_test() -> None:
    incumbent = _suite({f"c{i}": True for i in range(12)})
    candidate = _suite({f"c{i}": (i >= 10) for i in range(12)})
    diff = migration_diff(incumbent=incumbent, candidate=candidate)
    assert diff.mcnemar_p_value == pytest.approx(
        paired_eval_test(pass_to_fail=10, fail_to_pass=0)
    )


def test_a_mismatched_suite_is_a_setup_error() -> None:
    incumbent = _suite({"a": True, "b": True})
    candidate = _suite({"a": True, "c": True})  # different case set
    with pytest.raises(ValueError, match="identical frozen suite"):
        migration_diff(incumbent=incumbent, candidate=candidate)
