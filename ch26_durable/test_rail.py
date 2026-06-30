"""The rail honors the key: a repeat is a no-op. Offline fake, no spend."""

from __future__ import annotations

from decimal import Decimal

import pytest

from .rail import (
    IdempotentRail,
    RailRejection,
    RailResponse,
    RailTransientError,
    RejectingRail,
)


def test_a_repeated_key_returns_the_same_confirmation_and_does_not_pay_twice() -> None:
    rail = IdempotentRail()
    first = rail.transfer(
        account="000123456789", amount=Decimal("100.00"), idempotency_key="k-1"
    )
    second = rail.transfer(
        account="000123456789", amount=Decimal("100.00"), idempotency_key="k-1"
    )
    assert isinstance(first, RailResponse)
    assert second == first  # the dedup hit returned the original confirmation
    assert rail.transfer_count == 1  # money moved exactly once
    assert rail.call_count == 2  # but the rail was called twice


def test_distinct_keys_each_move_money() -> None:
    rail = IdempotentRail()
    rail.transfer(account="acct", amount=Decimal("1.00"), idempotency_key="k-1")
    rail.transfer(account="acct", amount=Decimal("2.00"), idempotency_key="k-2")
    assert rail.transfer_count == 2


def test_a_transient_fault_is_raised_for_the_caller_to_retry() -> None:
    rail = IdempotentRail(fail_transiently_times=1)
    with pytest.raises(RailTransientError):
        rail.transfer(account="acct", amount=Decimal("1.00"), idempotency_key="k-1")
    assert rail.transfer_count == 0  # nothing moved on the transient failure


def test_a_rejection_is_permanent() -> None:
    rail = RejectingRail()
    with pytest.raises(RailRejection):
        rail.transfer(account="acct", amount=Decimal("1.00"), idempotency_key="k-1")
