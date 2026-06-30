"""Step ③ — the bug reproduced offline, deterministically, on the real rail.

These pin the reproduction: under a *forced* retry, the buggy backwater double-pays
(two real transfers) while the threaded key the AP main path uses dedupes to one.
The only difference between the two is whether a stable key is threaded — which is
the bug, isolated. Reuses Chapter 26's real `IdempotentRail`; zero spend.
"""

from __future__ import annotations

import pytest

from autopilot import InvoiceId
from autopilot.fixtures import INVOICES
from ch26_durable.rail import IdempotentRail

from .reproduce import replay_payment

_INVOICE = INVOICES[InvoiceId("INV-1043")]


def test_the_unkeyed_backwater_double_pays_under_a_forced_retry() -> None:
    rail = IdempotentRail()
    replay_payment(invoice=_INVOICE, rail=rail, thread_key=False, attempts=2)
    assert rail.transfer_count == 2  # Tuesday: the retry minted a new payment


def test_the_threaded_key_pays_once_under_the_same_retry() -> None:
    rail = IdempotentRail()
    retried = replay_payment(invoice=_INVOICE, rail=rail, thread_key=True, attempts=2)
    assert rail.transfer_count == 1  # the rail deduped the retry — money moved once

    # The retry returns the FIRST confirmation, not a new one (Chapter 26's contract):
    # a single keyed attempt yields the identical confirmation_id.
    once = replay_payment(
        invoice=_INVOICE, rail=IdempotentRail(), thread_key=True, attempts=1
    )
    assert retried.confirmation_id == once.confirmation_id


def test_the_double_pay_is_reliable_not_a_one_off() -> None:
    # "Reliably red" (Chapter 21): the reproduction is deterministic, so every replay
    # of the buggy path double-pays — it is a bug, not noise.
    for _ in range(5):
        rail = IdempotentRail()
        replay_payment(invoice=_INVOICE, rail=rail, thread_key=False, attempts=2)
        assert rail.transfer_count == 2


def test_a_single_attempt_pays_once_either_way() -> None:
    # Without the forced retry there is no double-pay to see — the fault must be
    # injected, which is exactly why the harness forces it.
    for thread_key in (True, False):
        rail = IdempotentRail()
        replay_payment(invoice=_INVOICE, rail=rail, thread_key=thread_key, attempts=1)
        assert rail.transfer_count == 1


def test_attempts_must_be_positive() -> None:
    with pytest.raises(ValueError, match="attempts must be >= 1"):
        replay_payment(
            invoice=_INVOICE, rail=IdempotentRail(), thread_key=True, attempts=0
        )
