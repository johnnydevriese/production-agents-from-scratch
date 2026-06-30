"""The messy world on the far side of the airlock.

`POST /v3/disbursements` takes integer cents, an optional-but-fatal dedupe key,
and a `force` flag that bypasses the rail's own duplicate guard. None of that
should ever reach the model — it lives here, behind the facade. `RailClient` is a
Protocol so the facade takes its rail by injection; `FakeRail` records exactly
what was sent so a test can prove dollars became cents and `force` stayed False.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from pydantic import BaseModel


class DisburseResponse(BaseModel):
    value_date: date


class RailClient(Protocol):
    def disburse(
        self,
        *,
        payee_acct: str,
        amount_cents: int,
        external_ref: str,
        force: bool,
    ) -> DisburseResponse: ...


class DisburseCall(BaseModel):
    payee_acct: str
    amount_cents: int
    external_ref: str
    force: bool


class FakeRail:
    """A stand-in rail that records each disbursement instead of moving money."""

    def __init__(self, *, value_date: date) -> None:
        self._value_date = value_date
        self.calls: list[DisburseCall] = []

    def __repr__(self) -> str:
        return f"FakeRail(calls={len(self.calls)})"

    def disburse(
        self,
        *,
        payee_acct: str,
        amount_cents: int,
        external_ref: str,
        force: bool,
    ) -> DisburseResponse:
        self.calls.append(
            DisburseCall(
                payee_acct=payee_acct,
                amount_cents=amount_cents,
                external_ref=external_ref,
                force=force,
            )
        )
        return DisburseResponse(value_date=self._value_date)
