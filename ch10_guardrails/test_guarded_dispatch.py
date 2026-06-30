"""The attack lands but the gate holds — offline, against the real FakeRail facade.

The model may be fooled into PROPOSING schedule_payment with attacker-chosen
details. Proposing isn't paying: an unconfirmed money-movement call degrades to a
human via request_approval, and the rail never disburses. A human-set `confirmed`
flag — which the model can't produce — is the only thing that releases the money.
"""

from __future__ import annotations

from datetime import date

from autopilot.models import ApprovalRequest, InvoiceId, Payment
from ch06_facade.facade import RailPaymentFacade
from ch06_facade.rail import FakeRail

from .guarded_dispatch import settle_or_escalate


def _facade() -> tuple[RailPaymentFacade, FakeRail]:
    rail = FakeRail(value_date=date(2026, 6, 30))
    return RailPaymentFacade(rail=rail), rail


def test_unconfirmed_payment_escalates_and_never_disburses() -> None:
    facade, rail = _facade()
    outcome = settle_or_escalate(
        InvoiceId("INV-1043"),
        facade=facade,
        confirmed=False,  # the model can't set this; no human approved
        idempotency_key="k-1",
    )
    assert isinstance(outcome, ApprovalRequest)
    assert "money_movement" in outcome.reason
    assert rail.calls == []  # the load-bearing assertion: no money moved


def test_human_confirmation_releases_the_payment() -> None:
    facade, rail = _facade()
    outcome = settle_or_escalate(
        InvoiceId("INV-1043"),
        facade=facade,
        confirmed=True,  # a human clicked approve, outside the model's reach
        idempotency_key="k-1",
    )
    assert isinstance(outcome, Payment)
    assert len(rail.calls) == 1
    assert rail.calls[0].force is False  # the facade never bypasses the rail's guard
