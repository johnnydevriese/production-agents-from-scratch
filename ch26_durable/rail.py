"""A fake payments rail that honors an idempotency key — the other half of the contract.

The key is useless unless the rail *dedupes* on it: a repeated key must return the
SAME confirmation and move money once. This stand-in models exactly that guarantee
(real rails dedupe server-side for a retention window) plus the two error shapes that
the retry policy must tell apart — a *transient* fault you may retry under the same
key, and a *rejection* you must never retry.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel


class RailError(Exception):
    """Base for payments-rail failures."""


class RailTransientError(RailError):
    """A timeout, a 503, a dropped connection — safe to retry under the same key."""


class RailRejection(RailError):
    """A permanent refusal (insufficient funds, bad account). Retrying only burns budget."""


class RailResponse(BaseModel, frozen=True):
    """The rail's confirmation. The same key always yields the same confirmation_id."""

    confirmation_id: str
    value_date: date


class Rail(Protocol):
    """The transfer shape every payments rail honors — keyword-only, keyed, dedup-aware."""

    def transfer(
        self, *, account: str, amount: Decimal, idempotency_key: str
    ) -> RailResponse: ...


class IdempotentRail:
    """An in-memory rail that dedupes on `idempotency_key`.

    Tracks `transfer_count` — the number of times money *actually* moved — separately
    from how many times `transfer` was called, so a test can prove a replayed key was a
    no-op. Inject a `fail_transiently_times` to simulate a flaky rail for the retry test.
    """

    def __init__(self, *, fail_transiently_times: int = 0) -> None:
        self._seen: dict[str, RailResponse] = {}
        self._fails_left = fail_transiently_times
        self.transfer_count = 0  # real money movements
        self.call_count = (
            0  # every attempt, including dedup hits and transient failures
        )

    def __repr__(self) -> str:
        return (
            f"IdempotentRail(transfers={self.transfer_count}, seen={len(self._seen)})"
        )

    def transfer(
        self, *, account: str, amount: Decimal, idempotency_key: str
    ) -> RailResponse:
        """Move money once per key. A repeat key returns the original confirmation."""
        self.call_count += 1
        if idempotency_key in self._seen:
            return self._seen[idempotency_key]  # dedup: did NOT pay twice
        if self._fails_left > 0:
            self._fails_left -= 1
            raise RailTransientError(
                f"rail unavailable (account {account[-4:]}, {amount})"
            )
        self.transfer_count += 1
        resp = RailResponse(
            confirmation_id=f"conf-{idempotency_key[:12]}", value_date=date(2026, 7, 15)
        )
        self._seen[idempotency_key] = resp
        return resp


class RejectingRail:
    """A rail that permanently rejects — used to prove the retry policy does NOT retry."""

    def __init__(self) -> None:
        self.call_count = 0

    def __repr__(self) -> str:
        return f"RejectingRail(calls={self.call_count})"

    def transfer(
        self, *, account: str, amount: Decimal, idempotency_key: str
    ) -> RailResponse:
        self.call_count += 1
        raise RailRejection(
            f"insufficient funds for {amount} (account {account[-4:]}, key {idempotency_key[:8]})"
        )
