"""The release tuple, its id, the diff, and the kill switch.

These pin: the release_id is a stable hash of the behavior-determining triple, so a
one-word prompt edit changes it (the thing that's invisible if the prompt is a bare
literal); `diff_releases` answers "what changed?"; and the kill switch downgrades
money movement — and only money movement — to human approval. Pure, no spend.
"""

from __future__ import annotations

from autopilot import TOOL_RISK, RiskTier

from .release import AgentRelease, diff_releases, gated_tool, tool_surface_hash


_BASE = AgentRelease(
    prompt_text="You are an accounts-payable autopilot.",
    model_id="anthropic:claude-sonnet-5",
    tool_schema_hash=tool_surface_hash(),
    eval_suite_sha="abc123",
)


def _release(**overrides: object) -> AgentRelease:
    return _BASE.model_copy(update=overrides)


def test_the_release_id_is_stable_for_the_same_tuple() -> None:
    assert _release().release_id == _release().release_id


def test_a_one_word_prompt_edit_changes_the_release_id() -> None:
    before = _release()
    after = _release(prompt_text=before.prompt_text + " Be concise.")
    assert before.release_id != after.release_id  # the invisible change, made visible


def test_the_model_id_is_part_of_the_behavior_hash() -> None:
    # A forced model migration is a behavioral change — a new id, a new release.
    assert _release().release_id != _release(model_id="openai:gpt-5").release_id


def test_the_eval_suite_sha_is_not_part_of_the_behavior_id() -> None:
    # The id pins what changes behavior; which suite it passed is metadata.
    assert _release().release_id == _release(eval_suite_sha="different").release_id


def test_diff_releases_names_exactly_what_changed() -> None:
    old = _release()
    new = _release(model_id="openai:gpt-5", kill_switch=True)
    diff = diff_releases(old, new)
    assert set(diff) == {"model_id", "kill_switch"}
    assert diff["model_id"] == ("anthropic:claude-sonnet-5", "openai:gpt-5")


def test_the_kill_switch_downgrades_money_movement_to_approval() -> None:
    flipped = _release(kill_switch=True)
    assert gated_tool(flipped, "schedule_payment") == "request_approval"
    # Read-only tools are untouched — the switch is surgical, not a full stop.
    assert gated_tool(flipped, "lookup_invoice") == "lookup_invoice"


def test_the_kill_switch_is_a_noop_when_off() -> None:
    assert gated_tool(_release(), "schedule_payment") == "schedule_payment"


def test_the_tool_surface_hash_tracks_the_real_menu() -> None:
    # The hash is over the live TOOL_RISK table, and schedule_payment is money-tier.
    assert TOOL_RISK["schedule_payment"] is RiskTier.MONEY_MOVEMENT
    assert len(tool_surface_hash()) == 12
