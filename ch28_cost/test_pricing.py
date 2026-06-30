"""Token economics — pure arithmetic over a usage block. No model, no spend.

These pin that the four token streams are priced separately: a cache *read* is far
cheaper than a fresh input token, a cache *write* is dearer — which is exactly why
the amortization in `cached_prompt.py` has to count reads against writes.
"""

from __future__ import annotations

from decimal import Decimal

from .pricing import ModelPricing, Usage, cost_of

_MID = ModelPricing.standard("mid", input_per_1k="0.003", output_per_1k="0.015")


def test_cost_charges_input_and_output_at_their_own_rates() -> None:
    usage = Usage(input_tokens=1000, output_tokens=1000)
    assert cost_of(usage, pricing=_MID) == Decimal("0.018")  # 0.003 + 0.015


def test_a_cache_read_is_cheaper_than_a_fresh_input_token() -> None:
    fresh = cost_of(Usage(input_tokens=1000, output_tokens=0), pricing=_MID)
    cached = cost_of(
        Usage(input_tokens=0, output_tokens=0, cache_read_input_tokens=1000),
        pricing=_MID,
    )
    assert cached < fresh


def test_a_cache_write_costs_more_than_a_fresh_input_token() -> None:
    fresh = cost_of(Usage(input_tokens=1000, output_tokens=0), pricing=_MID)
    write = cost_of(
        Usage(input_tokens=0, output_tokens=0, cache_creation_input_tokens=1000),
        pricing=_MID,
    )
    assert write > fresh


def test_standard_pricing_sets_the_usual_cache_premium_and_discount() -> None:
    assert _MID.cache_write_per_1k == Decimal("0.003") * Decimal("1.25")
    assert _MID.cache_read_per_1k == Decimal("0.003") * Decimal("0.1")
