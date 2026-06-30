"""Facade tests — pure (T1): no LLM, no network, no spend.

These are the high-value tests of the chapter: the off-by-100 catastrophe is
impossible *by construction*, `force` is never True, and the dedupe key is
threaded verbatim. None of it needs a model, because the facade owns execution,
not reasoning.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from autopilot.models import InvoiceId
from autopilot.tools import AutopilotTools

from .facade import RailPaymentFacade
from .rail import FakeRail


def _facade() -> tuple[RailPaymentFacade, FakeRail]:
    rail = FakeRail(value_date=date(2026, 7, 12))
    return RailPaymentFacade(rail=rail), rail


def test_facade_is_a_structural_autopilot_tools() -> None:
    # Static conformance is checked by basedpyright; this binds it at runtime too.
    facade, _rail = _facade()
    tools: AutopilotTools = facade
    assert hasattr(tools, "schedule_payment")


def test_dollars_become_cents_exactly_once_in_code_you_can_test() -> None:
    facade, rail = _facade()

    facade.schedule_payment(InvoiceId("INV-1043"), idempotency_key="pay-INV-1043-1")

    # $2,988.09 → 298809 cents, never 29880900 or 2988.
    assert rail.calls[-1].amount_cents == 298809


def test_force_is_never_true() -> None:
    facade, rail = _facade()
    facade.schedule_payment(InvoiceId("INV-1043"), idempotency_key="k")
    assert rail.calls[-1].force is False


def test_idempotency_key_is_threaded_as_the_dedupe_ref() -> None:
    facade, rail = _facade()
    facade.schedule_payment(InvoiceId("INV-1043"), idempotency_key="pay-INV-1043-42")
    assert rail.calls[-1].external_ref == "pay-INV-1043-42"


def test_payment_is_typed_and_grounded_in_the_invoice() -> None:
    facade, _rail = _facade()
    payment = facade.schedule_payment(
        InvoiceId("INV-1043"), idempotency_key="pay-INV-1043-1"
    )
    assert payment.amount == Decimal("2988.09")
    assert payment.scheduled_for == date(2026, 7, 12)


def test_bank_account_reaches_the_rail_but_never_a_repr() -> None:
    facade, rail = _facade()
    facade.schedule_payment(InvoiceId("INV-1043"), idempotency_key="k")
    # The rail got the real account…
    assert rail.calls[-1].payee_acct == "000123456789"
    # …but the secret never lands in a vendor repr (Field(repr=False), Ch 29).
    assert "000123456789" not in repr(
        facade.get_vendor(facade.lookup_invoice(InvoiceId("INV-1043")).vendor_id)
    )
