"""A deterministic idempotency key — the identity of the work, not the wall clock.

The key is not a fresh UUID per call (that would defeat the point) and never depends
on `now()` or `random`. It is a pure function of *which payment this is*, so a
crash-and-retry — or a durable workflow replaying its history — reproduces the exact
same string and the rail recognizes the repeat. The basis includes the tenant,
environment, rail, payee, payment type, amount, and currency: the same invoice in a
test tenant must not dedupe a production payment, and the same vendor on a different
rail may be a different side effect. The amount is in the basis on purpose: if a
human edits the invoice total during approval (Chapter 27), the corrected payment is
a genuinely *different* payment and earns a *different* key.
"""

from __future__ import annotations

import hashlib

from autopilot import Invoice

_DEFAULT_TENANT = "demo-tenant"
_DEFAULT_ENVIRONMENT = "test"
_DEFAULT_RAIL = "fake-ach"
_DEFAULT_PAYMENT_TYPE = "invoice_payment"


def payment_idempotency_key(
    invoice: Invoice,
    *,
    tenant_id: str = _DEFAULT_TENANT,
    environment: str = _DEFAULT_ENVIRONMENT,
    rail: str = _DEFAULT_RAIL,
    payment_type: str = _DEFAULT_PAYMENT_TYPE,
) -> str:
    """A stable key for paying THIS invoice on THIS rail for THIS tenant.

    Deterministic, not random: a crash-and-retry (or a workflow replay) must
    reproduce it exactly, or the rail can't tell the retry from a new payment.
    """
    basis = ":".join(
        (
            "pay",
            tenant_id,
            environment,
            rail,
            payment_type,
            str(invoice.vendor_id),
            str(invoice.id),
            str(invoice.total),
            invoice.currency,
        )
    )
    return hashlib.sha256(basis.encode()).hexdigest()  # stable across restarts
