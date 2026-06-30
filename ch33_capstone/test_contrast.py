"""The orchestration-vs-coding refrain, asserted on the real agents.

These pin the bottom rows of the chapter's comparison table: the AP autopilot is a
bounded menu of typed tools, one of which moves money; the analyst is a single
unbounded sandbox tool that can never move money. Introspection only — the agents
are imported and read, never run; zero spend.
"""

from __future__ import annotations

from autopilot import TOOL_RISK, RiskTier
from ch11_framework.agent import autopilot

from .contrast import analyst_profile, autopilot_profile, registered_tools


def test_the_autopilot_is_a_bounded_typed_menu() -> None:
    ap = autopilot_profile()
    assert ap.bounded
    # The seven typed actions frozen since Chapter 3 (extract_invoice is added later
    # and isn't registered on this agent).
    assert ap.tools == {
        "lookup_invoice",
        "get_vendor",
        "match_to_po",
        "check_budget",
        "request_approval",
        "schedule_payment",
        "post_journal_entry",
    }


def test_the_analyst_is_one_unbounded_tool() -> None:
    analyst = analyst_profile()
    assert not analyst.bounded
    assert analyst.tools == {"run_python"}
    assert analyst.tool_count == 1


def test_only_the_autopilot_can_move_money() -> None:
    # The whole second refrain in one assertion: bounded menu holds a money tool;
    # the unbounded sandbox holds none.
    assert autopilot_profile().can_move_money
    assert not analyst_profile().can_move_money


def test_the_analyst_holds_no_classified_tool_at_all() -> None:
    # Its safety model is sandbox isolation, not risk tiers — run_python isn't even
    # in TOOL_RISK, so it cannot act on the world through the AP tool surface.
    assert all(tool not in TOOL_RISK for tool in analyst_profile().tools)


def test_money_movement_lives_only_in_the_autopilots_menu() -> None:
    money_tools = {
        tool for tool, tier in TOOL_RISK.items() if tier is RiskTier.MONEY_MOVEMENT
    }
    assert money_tools <= registered_tools(autopilot)
    assert not (money_tools & analyst_profile().tools)
