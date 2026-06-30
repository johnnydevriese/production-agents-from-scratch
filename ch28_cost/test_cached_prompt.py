"""Prompt caching — the exact-prefix rule and the amortization bet. Pure, no spend.

These pin the two ways caching is won or lost: the cache matches *exact* bytes (one
changed character of the system prompt, or a wobble in tool-schema key order, is a
silent miss), and the premium write only pays off once it's amortized over reads —
so caching helps the multi-turn loop and can *lose* on a one-shot call.
"""

from __future__ import annotations

from .cached_prompt import (
    build_cached_system,
    preamble_cost,
    prefix_fingerprint,
    would_cache_hit,
)
from .pricing import ModelPricing

_MID = ModelPricing.standard("mid", input_per_1k="0.003", output_per_1k="0.015")
_TOOLS = [{"name": "lookup_invoice", "description": "fetch one invoice"}]


def test_the_stable_prefix_is_marked_cacheable() -> None:
    block = build_cached_system("You are the AP autopilot.")
    assert block[0]["cache_control"] == {"type": "ephemeral"}


def test_an_identical_prefix_hits() -> None:
    a = prefix_fingerprint(system_prompt="standing instructions", tool_schemas=_TOOLS)
    b = prefix_fingerprint(system_prompt="standing instructions", tool_schemas=_TOOLS)
    assert would_cache_hit(previous_key=a, current_key=b)


def test_one_changed_character_misses() -> None:
    a = prefix_fingerprint(system_prompt="standing instructions", tool_schemas=_TOOLS)
    b = prefix_fingerprint(system_prompt="standing instructions.", tool_schemas=_TOOLS)
    assert not would_cache_hit(previous_key=a, current_key=b)  # the exact-prefix rule


def test_a_tool_schema_key_wobble_misses() -> None:
    reordered = [{"description": "fetch one invoice", "name": "lookup_invoice"}]
    a = prefix_fingerprint(system_prompt="instructions", tool_schemas=_TOOLS)
    b = prefix_fingerprint(system_prompt="instructions", tool_schemas=reordered)
    assert not would_cache_hit(previous_key=a, current_key=b)  # the silent footgun


def test_caching_wins_across_the_loops_turns() -> None:
    uncached = preamble_cost(preamble_tokens=1400, turns=6, pricing=_MID, cached=False)
    cached = preamble_cost(preamble_tokens=1400, turns=6, pricing=_MID, cached=True)
    assert cached < uncached


def test_caching_can_lose_on_a_one_shot_call() -> None:
    # One turn: you pay the premium write and never read it back.
    uncached = preamble_cost(preamble_tokens=1400, turns=1, pricing=_MID, cached=False)
    cached = preamble_cost(preamble_tokens=1400, turns=1, pricing=_MID, cached=True)
    assert cached > uncached
