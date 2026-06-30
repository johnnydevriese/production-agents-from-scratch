"""Lever 2 — model tiers and the cascade: cheap by default, expensive on demand.

Not every step needs the frontier model. `extract_invoice` on a clean, text-
extractable invoice is a structured-output task a small model nails; reasoning about
a genuine PO mismatch is a judgment call worth frontier prices. The cascade does the
cheap thing first and falls *up* only when the cheap tier signals it's out of its
depth — the same shape Chapter 14 used for routing, applied to model choice.

The tier callables are injected, so the escalation logic is testable with zero spend.
A miscalibrated threshold is the failure mode: too low never escalates and errs on the
hard tail; too high never saves money. You calibrate it against the labeled suite of
Part VII, never by trying three invoices and liking the result.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from pydantic import BaseModel, Field

from autopilot.models import Invoice


class Tier(str, Enum):
    CHEAP = "cheap"
    FRONTIER = "frontier"


class Extraction(BaseModel):
    """One tier's attempt, with the self-reported confidence the cascade gates on."""

    invoice: Invoice
    confidence: float = Field(ge=0, le=1)


class CascadeResult(BaseModel):
    invoice: Invoice
    tier_used: Tier
    escalated: bool


Extractor = Callable[[str], Extraction]


def extract_with_cascade(
    invoice_text: str,
    *,
    cheap: Extractor,
    frontier: Extractor,
    threshold: float = 0.92,
) -> CascadeResult:
    """Try the cheap model; escalate to the frontier model only when unconfident."""
    first = cheap(invoice_text)
    if first.confidence >= threshold:
        return CascadeResult(
            invoice=first.invoice, tier_used=Tier.CHEAP, escalated=False
        )
    second = frontier(invoice_text)
    return CascadeResult(
        invoice=second.invoice, tier_used=Tier.FRONTIER, escalated=True
    )
