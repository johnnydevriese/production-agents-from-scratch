"""Lever 4 — batch vs on-demand: the overnight job has no one waiting.

The 40k-invoice overnight ingestion is not interactive — only the 5 a.m. cutoff cares
about latency. On-demand calls are priced for an urgency this job doesn't have. The
async batch tier trades latency for roughly a 50% discount, exactly the trade the
overnight job wants.

But not every step fits: a step that must call a *real* tool mid-loop —
`schedule_payment`, which moves money inside the durable workflow — can't be a
fire-and-forget batch completion. So batchability reads straight off the frozen risk
taxonomy: read-only, decision-light steps batch; anything that writes, moves money,
or talks to the outside world does not. Batch the thinking; don't batch the wire
transfer.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from autopilot.tools import TOOL_RISK, RiskTier

BATCH_RATE = Decimal("0.5")  # ~50% of the on-demand price; exact discount varies

# The Ch 9 extraction *capability* isn't in TOOL_RISK, but it's pure read/extract.
_EXTRA_BATCHABLE = frozenset({"extract_invoice"})


class BatchEstimate(BaseModel):
    """The cost of the same agent logic run on-demand vs as one async batch job."""

    on_demand: Decimal
    batch: Decimal
    saved: Decimal


def estimate_batch_savings(
    *, n_invoices: int, per_invoice_cost: Decimal
) -> BatchEstimate:
    """Two ways to pay for the overnight job: synchronous now, or async by 5 a.m."""
    on_demand = per_invoice_cost * Decimal(n_invoices)
    batch = on_demand * BATCH_RATE
    return BatchEstimate(on_demand=on_demand, batch=batch, saved=on_demand - batch)


def is_batchable(step: str) -> bool:
    """True when a step is safe to run on the async tier (read-heavy, decision-light).

    Money-movement, irreversible writes, and external comms are not — they belong to
    the durable workflow's synchronous tail, not a fire-and-forget batch.
    """
    if step in _EXTRA_BATCHABLE:
        return True
    tier = TOOL_RISK.get(step)
    if tier is None:
        raise KeyError(f"unknown step: {step!r}")
    return tier is RiskTier.READ_ONLY
