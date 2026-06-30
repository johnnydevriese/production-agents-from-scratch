"""Read the bill off the trace: sum the per-span usage into a per-invoice budget.

The abstract "the bill blew up" resolves into a line-item you can attack once you sum
`gen_ai.usage.*` across one invoice's spans. Two facts do the whole diagnosis: input
tokens dominate output ~18:1 (so shave input, not output), and a fixed preamble —
the ~1,400-token system prompt plus tool schemas — rides along on *every* loop turn,
because the conversation is stateless and you re-send the context each time. That
re-sent preamble is the biggest, most boring line item, and the one prompt caching
exists to kill.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from pydantic import BaseModel

from .pricing import ModelPricing, Usage, cost_of


class InvoiceBill(BaseModel):
    """The summed cost of every model call on one invoice's trace."""

    calls: int
    total_input_tokens: int
    total_output_tokens: int
    cost: Decimal

    @property
    def input_output_ratio(self) -> float:
        """How lopsided the bill is. >1 means input dominates — aim optimizations there."""
        if self.total_output_tokens == 0:
            return float("inf")
        return self.total_input_tokens / self.total_output_tokens


def summarize_invoice(usages: Sequence[Usage], *, pricing: ModelPricing) -> InvoiceBill:
    """Fold the per-span usage of one invoice into a single attackable line-item."""
    return InvoiceBill(
        calls=len(usages),
        total_input_tokens=sum(u.input_tokens for u in usages),
        total_output_tokens=sum(u.output_tokens for u in usages),
        cost=sum((cost_of(u, pricing=pricing) for u in usages), Decimal(0)),
    )


def preamble_tax(*, preamble_tokens: int, loop_turns: int) -> int:
    """Input tokens paid for *re-sending* the fixed preamble across the loop.

    The first turn has to send it once; every turn after re-sends the same bytes.
    This is exactly the quantity prompt caching converts into cheap reads.
    """
    if loop_turns <= 0:
        return 0
    return preamble_tokens * (loop_turns - 1)
