"""The divide, asserted. Pure (T1): no client, no network, no spend.

The point of the chapter is that the bounded agent's harmful surface is a finite
list you can write a test that fails if a third name ever appears. So we do
exactly that.
"""

from __future__ import annotations

from autopilot.tools import RiskTier, TOOL_RISK

from .action_space import describe_bounded, describe_unbounded


def test_bounded_worst_case_is_exactly_two_named_actions() -> None:
    report = describe_bounded()
    assert "Total actions: 7" in report
    # The whole argument: the direct harmful set is visible and pinned by a test.
    assert "['post_journal_entry', 'schedule_payment']" in report


def test_a_new_money_tool_would_break_this_test() -> None:
    # Guard the canon: only these two tiers are human-gated, and only two tools
    # carry them. If someone adds a third, this fails loudly — by design.
    gated = {
        name
        for name, tier in TOOL_RISK.items()
        if tier in {RiskTier.MONEY_MOVEMENT, RiskTier.IRREVERSIBLE_WRITE}
    }
    assert gated == {"schedule_payment", "post_journal_entry"}


def test_unbounded_worst_case_cannot_be_a_list() -> None:
    report = describe_unbounded()
    assert "Total actions: 1" in report
    # It's a string, not a list — because the set it describes is not finite.
    assert "anything the interpreter can reach" in report
