"""Lever 1 — prompt caching: stop paying for the same tokens twice.

The system prompt and tool schemas are byte-identical on every call within an
invoice and across invoices. Mark that stable prefix cacheable and later calls read
it at a steep discount instead of re-ingesting it. Two rules make or break it, and
both are modeled here as pure functions:

- **The cache is prefix-matched and *exact*.** Change one character of the system
  prompt — or let a tool schema's key order wobble between serializations — and the
  prefix no longer matches, the cache misses, and you quietly pay full price. The
  fingerprint here is over the *exact* bytes, so a wobble flips a hit to a miss.
- **A write costs more than a normal call; a read costs much less.** Caching bets
  the prefix is reused enough to amortize the premium write. Across the loop's turns
  the bet is overwhelmingly correct; on a one-shot call it can be a net loss.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from types import MappingProxyType

from .pricing import ModelPricing

CACHE_CONTROL: Mapping[str, str] = MappingProxyType({"type": "ephemeral"})


def build_cached_system(system_prompt: str) -> list[dict[str, object]]:
    """Wrap the standing instructions as a single cacheable system block.

    The large, stable content goes first; the variable content (the specific invoice)
    rides in `messages`, never here — that ordering is what keeps the prefix stable.
    """
    return [
        {"type": "text", "text": system_prompt, "cache_control": dict(CACHE_CONTROL)}
    ]


def prefix_fingerprint(
    *, system_prompt: str, tool_schemas: Sequence[Mapping[str, object]]
) -> str:
    """A fingerprint over the *exact* cacheable prefix bytes.

    Deliberately not canonicalized: the provider cache matches raw bytes, so if the
    tool-schema serialization reorders its keys the real cache misses — and so does
    this fingerprint. That is the footgun, made visible.
    """
    payload = system_prompt + "\x00" + json.dumps(list(tool_schemas))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def would_cache_hit(*, previous_key: str, current_key: str) -> bool:
    """A cache hit requires a byte-identical prefix — nothing softer."""
    return previous_key == current_key


def preamble_cost(
    *, preamble_tokens: int, turns: int, pricing: ModelPricing, cached: bool
) -> Decimal:
    """Cost of the *preamble portion* across a loop, cached vs not.

    Uncached, every turn re-sends the preamble at the full input rate. Cached, turn
    one writes it (premium) and every later turn reads it (cheap) — so the write is
    amortized over the reads, and the bet pays off the moment there are two turns.
    """
    tokens = Decimal(preamble_tokens) / Decimal(1000)
    if not cached:
        return pricing.input_per_1k * tokens * Decimal(turns)
    reads = max(turns - 1, 0)
    return (
        pricing.cache_write_per_1k * tokens
        + pricing.cache_read_per_1k * tokens * Decimal(reads)
    )
