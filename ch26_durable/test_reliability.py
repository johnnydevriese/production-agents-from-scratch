"""Retry transient faults only; fall back by risk tier. Pure, instant (no real backoff), no spend."""

from __future__ import annotations

from decimal import Decimal

import pytest
from tenacity import wait_none

from .rail import IdempotentRail, RailRejection, RailTransientError, RejectingRail
from .reliability import Fallback, fallback_for, is_transient, transfer_with_retry


def test_a_transient_fault_is_retried_under_the_same_key_until_it_succeeds() -> None:
    rail = IdempotentRail(fail_transiently_times=2)  # flaky twice, then OK
    resp = transfer_with_retry(
        rail,
        account="000123456789",
        amount=Decimal("100.00"),
        idempotency_key="k-1",
        wait=wait_none(),  # no real sleeping in the test
    )
    assert resp.confirmation_id.startswith("conf-")
    assert rail.transfer_count == 1  # the same key throughout → money moved once
    assert rail.call_count == 3  # two transient failures + the success


def test_a_rejection_is_not_retried() -> None:
    rail = RejectingRail()  # satisfies the Rail protocol; always rejects
    with pytest.raises(RailRejection):
        transfer_with_retry(
            rail,
            account="acct",
            amount=Decimal("1.00"),
            idempotency_key="k-1",
            wait=wait_none(),
        )
    assert rail.call_count == 1  # permanent: tried exactly once, never retried


def test_is_transient_separates_the_two_failure_shapes() -> None:
    assert is_transient(RailTransientError("timeout"))
    assert not is_transient(RailRejection("insufficient funds"))


def test_a_read_only_step_degrades_but_a_money_step_escalates_to_a_human() -> None:
    assert fallback_for("lookup_invoice") is Fallback.DEGRADE  # cached value / report
    assert fallback_for("schedule_payment") is Fallback.ESCALATE  # STOP, ask a human
    assert fallback_for("post_journal_entry") is Fallback.ESCALATE


def test_an_unknown_tool_fails_closed() -> None:
    with pytest.raises(KeyError):
        fallback_for("teleport_funds")
