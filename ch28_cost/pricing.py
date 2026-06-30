"""Token economics: turn a `usage` block into dollars.

The `usage` on every call is the bill. Providers price four distinct token streams,
and conflating them is how a caching "win" turns into a loss: a *cache write* costs
more than an ordinary input token, a *cache read* costs much less, and you only come
out ahead when reads outnumber writes. This module keeps the four rates separate so
the amortization math in `cached_prompt.py` is honest.

Rates are per-1k-token `Decimal`s — representative tiers, not a live price sheet
(see Appendix A). Money is `Decimal`, never `float`.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class Usage(BaseModel):
    """The token counts a single call reports — the bill, itemized."""

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_creation_input_tokens: int = Field(default=0, ge=0)  # writing the prefix
    cache_read_input_tokens: int = Field(default=0, ge=0)  # reading it back, cheap

    @property
    def billed_input_tokens(self) -> int:
        """Fresh input tokens — what you'd pay full input rate for."""
        return self.input_tokens


class ModelPricing(BaseModel):
    """Per-1k-token rates for one model tier. A cache write is a premium on input."""

    name: str
    input_per_1k: Decimal
    output_per_1k: Decimal
    cache_write_per_1k: Decimal
    cache_read_per_1k: Decimal

    @classmethod
    def standard(
        cls, name: str, *, input_per_1k: str, output_per_1k: str
    ) -> ModelPricing:
        """Build a tier with the usual cache premium (1.25× write) and discount (0.1× read)."""
        inp = Decimal(input_per_1k)
        return cls(
            name=name,
            input_per_1k=inp,
            output_per_1k=Decimal(output_per_1k),
            cache_write_per_1k=inp * Decimal("1.25"),
            cache_read_per_1k=inp * Decimal("0.1"),
        )


def _per_token(rate_per_1k: Decimal, tokens: int) -> Decimal:
    return rate_per_1k * Decimal(tokens) / Decimal(1000)


def cost_of(usage: Usage, *, pricing: ModelPricing) -> Decimal:
    """Dollar cost of one call, charging each token stream at its own rate."""
    return (
        _per_token(pricing.input_per_1k, usage.input_tokens)
        + _per_token(pricing.output_per_1k, usage.output_tokens)
        + _per_token(pricing.cache_write_per_1k, usage.cache_creation_input_tokens)
        + _per_token(pricing.cache_read_per_1k, usage.cache_read_input_tokens)
    )
