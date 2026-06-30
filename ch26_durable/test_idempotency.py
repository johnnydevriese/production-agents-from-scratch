"""The key is the identity of the work — deterministic, edit-sensitive. Pure, no spend."""

from __future__ import annotations

import hashlib
from decimal import Decimal

from autopilot import InvoiceId
from autopilot.fixtures import INVOICES

from .idempotency import payment_idempotency_key

_INVOICE = INVOICES[InvoiceId("INV-1043")]


def test_the_same_invoice_yields_the_same_key_across_calls() -> None:
    # A crash-and-retry recomputes the identical key — that is the whole contract.
    assert payment_idempotency_key(_INVOICE) == payment_idempotency_key(_INVOICE)


def test_the_key_is_a_pure_hash_of_the_works_identity_not_a_random_uuid() -> None:
    basis = (
        "pay:demo-tenant:test:fake-ach:invoice_payment:"
        f"{_INVOICE.vendor_id}:{_INVOICE.id}:{_INVOICE.total}:{_INVOICE.currency}"
    )
    assert (
        payment_idempotency_key(_INVOICE) == hashlib.sha256(basis.encode()).hexdigest()
    )


def test_editing_the_amount_produces_a_different_key() -> None:
    # A human correction during approval makes it a genuinely different payment.
    corrected = _INVOICE.model_copy(
        update={"total": _INVOICE.total + Decimal("100.00")}
    )
    assert payment_idempotency_key(corrected) != payment_idempotency_key(_INVOICE)


def test_a_different_currency_produces_a_different_key() -> None:
    eur = _INVOICE.model_copy(update={"currency": "EUR"})
    assert payment_idempotency_key(eur) != payment_idempotency_key(_INVOICE)


def test_a_different_tenant_or_rail_produces_a_different_key() -> None:
    assert payment_idempotency_key(
        _INVOICE, tenant_id="tenant-a"
    ) != payment_idempotency_key(_INVOICE, tenant_id="tenant-b")
    assert payment_idempotency_key(
        _INVOICE, rail="ach"
    ) != payment_idempotency_key(_INVOICE, rail="wire")
