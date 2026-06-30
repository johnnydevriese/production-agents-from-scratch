"""The cascade decision — pure, tiers injected. No model, no spend.

These pin that the frontier model is paid for *only on the hard tail*: a confident
cheap extraction never reaches the frontier (a frontier that raises if called proves
it, the Chapter 13 pattern), and an unconfident one escalates. The threshold is a
`>=` boundary.
"""

from __future__ import annotations

from autopilot import InvoiceId
from autopilot.fixtures import INVOICES

from .cascade import Extraction, Tier, extract_with_cascade

_INVOICE = INVOICES[InvoiceId("INV-1043")]


def _cheap_confident(_: str) -> Extraction:
    return Extraction(invoice=_INVOICE, confidence=0.95)


def _cheap_unsure(_: str) -> Extraction:
    return Extraction(invoice=_INVOICE, confidence=0.40)


def _frontier_raises(_: str) -> Extraction:
    raise AssertionError("frontier model must not be called on a confident cheap pass")


def _frontier_ok(_: str) -> Extraction:
    return Extraction(invoice=_INVOICE, confidence=0.99)


def test_a_confident_cheap_pass_never_touches_the_frontier() -> None:
    result = extract_with_cascade(
        "clean invoice text", cheap=_cheap_confident, frontier=_frontier_raises
    )
    assert result.tier_used is Tier.CHEAP
    assert not result.escalated


def test_an_unconfident_cheap_pass_escalates() -> None:
    result = extract_with_cascade(
        "messy invoice text", cheap=_cheap_unsure, frontier=_frontier_ok
    )
    assert result.tier_used is Tier.FRONTIER
    assert result.escalated


def test_confidence_at_the_threshold_stays_cheap() -> None:
    def _at_threshold(_: str) -> Extraction:
        return Extraction(invoice=_INVOICE, confidence=0.92)

    result = extract_with_cascade(
        "borderline", cheap=_at_threshold, frontier=_frontier_raises, threshold=0.92
    )
    assert result.tier_used is Tier.CHEAP
