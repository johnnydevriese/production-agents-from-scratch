"""Step ③ — make the bug fail on demand, offline.

You cannot fix what you cannot reproduce, and you must reproduce it *offline*:
re-running the incident against production would move real money. The reproduction
needs the **fault** injected too, not just the inputs — here, the retry that fired
a second payment. So the harness *forces* the payment call to run twice (in
production that retry was incidental) and shows the double-pay is deterministic.

The mechanism is exactly Chapter 26's idempotency contract, run in reverse. The AP
agent's main path threads a *deterministic* `payment_idempotency_key`, so a forced
re-execution reproduces the same key and the rail dedupes — money moves once. The
reporting agent's payment path was a backwater that never got that wiring, so each
attempt minted a fresh key and the rail saw a *new* payment — money moved twice. We
reuse the real `IdempotentRail` and `payment_idempotency_key`; only the key
*threading* differs between the buggy path and the fixed one, and that single
difference is the whole bug.
"""

from __future__ import annotations

import hashlib

from autopilot import Invoice
from ch26_durable.idempotency import payment_idempotency_key
from ch26_durable.rail import IdempotentRail, RailResponse


def _unkeyed(invoice: Invoice, attempt: int) -> str:
    """The buggy backwater: a fresh key per attempt, so a retry looks like a new
    payment. Derived from the attempt index (deterministic, never random) — it stands
    in for the UUID-per-call a path that never threaded a stable key would mint."""
    return hashlib.sha256(f"{invoice.id}:attempt:{attempt}".encode()).hexdigest()


def replay_payment(
    *,
    invoice: Invoice,
    rail: IdempotentRail,
    thread_key: bool,
    attempts: int = 2,
) -> RailResponse:
    """Pay an invoice with a forced retry — the deterministic reproduction.

    With `thread_key=True` (the AP main path) every attempt uses the same
    deterministic key, so the rail dedupes the retry. With `thread_key=False` (the
    reporting backwater) each attempt mints a fresh key, so the retry is a *new*
    payment. The rail's `transfer_count` is the verdict: 1 is correct, 2 is Tuesday.
    """
    if attempts < 1:
        raise ValueError(f"attempts must be >= 1, got {attempts}")
    stable_key = payment_idempotency_key(invoice)
    response: RailResponse | None = None
    for attempt in range(attempts):
        key = stable_key if thread_key else _unkeyed(invoice, attempt)
        response = rail.transfer(
            account="000123456789", amount=invoice.total, idempotency_key=key
        )
    assert response is not None  # attempts >= 1 guaranteed at least one transfer
    return response
