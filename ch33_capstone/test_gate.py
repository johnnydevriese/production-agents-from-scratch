"""The runtime risk gate — `TOOL_RISK` as a human-in-the-loop decision.

These pin: read-only tools skip payment approval; the three dangerous tiers require a human;
and an unclassified tool fails *loud* (KeyError) instead of defaulting to safe.
Pure, no spend.
"""

from __future__ import annotations

import pytest

from autopilot import TOOL_RISK, RiskTier

from .gate import HIGH_RISK, requires_human


def test_read_only_tools_run_without_a_human() -> None:
    assert not requires_human("lookup_invoice")
    assert not requires_human("check_budget")  # the fact Chapter 1 hallucinated


def test_money_movement_requires_a_human() -> None:
    assert requires_human("schedule_payment")


def test_the_irreversible_and_external_tiers_require_a_human() -> None:
    assert requires_human("post_journal_entry")  # IRREVERSIBLE_WRITE
    assert requires_human("request_approval")  # EXTERNAL_COMMS


def test_an_unclassified_tool_fails_loud_not_safe() -> None:
    # extract_invoice is a separate capability and deliberately not in the table.
    assert "extract_invoice" not in TOOL_RISK
    with pytest.raises(KeyError):
        requires_human("extract_invoice")


def test_high_risk_is_exactly_the_three_dangerous_tiers() -> None:
    assert HIGH_RISK == {
        RiskTier.MONEY_MOVEMENT,
        RiskTier.IRREVERSIBLE_WRITE,
        RiskTier.EXTERNAL_COMMS,
    }


def test_every_classified_tool_gates_consistently_with_its_tier() -> None:
    # The gate is the table, nothing more: no tool is special-cased.
    for tool, tier in TOOL_RISK.items():
        assert requires_human(tool) == (tier in HIGH_RISK)
