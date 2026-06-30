"""The cheap reliability moves: retry transient faults only, fall back by risk tier.

Two traps the chapter calls out, both enforced here:

1. **Retry only transient faults.** A timeout or a 503 is transient; a rejection
   (insufficient funds, bad account) is *permanent* — retrying it burns budget and
   delays the inevitable. `transfer_with_retry` retries `RailTransientError` and lets
   `RailRejection` propagate on the first attempt.
2. **Fall back by risk tier, never silently.** When a step exhausts its retries, what
   happens next is a risk-tier decision read from the frozen `TOOL_RISK`: a `READ_ONLY`
   lookup may degrade to a cached value; anything privileged — above all
   `MONEY_MOVEMENT` — must STOP and route to a human. "Assume it worked" is how you
   launder a bug into a loss.

The retry is sound *only* because the same `idempotency_key` flows through every
attempt (see `idempotency`): a retry without it turns one crash into four duplicate
payments.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tenacity.wait import wait_base

from autopilot import TOOL_RISK, RiskTier

from .rail import Rail, RailResponse, RailTransientError


def is_transient(error: Exception) -> bool:
    """A transient fault is safe to retry under the same idempotency key; a rejection
    is not. Only the first kind earns a second attempt."""
    return isinstance(error, RailTransientError)


def transfer_with_retry(
    rail: Rail,
    *,
    account: str,
    amount: Decimal,
    idempotency_key: str,
    attempts: int = 4,
    wait: wait_base | None = None,
) -> RailResponse:
    """Transfer, retrying transient faults only and replaying the SAME key each time.

    A `RailRejection` is permanent and propagates on the first attempt (never retried).
    `wait` is injectable so tests run instantly; production uses exponential backoff.
    """
    controller = Retrying(
        stop=stop_after_attempt(attempts),
        wait=wait
        if wait is not None
        else wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(RailTransientError),
        reraise=True,  # surface the real error, not tenacity's RetryError wrapper
    )
    return controller(
        rail.transfer,
        account=account,
        amount=amount,
        idempotency_key=idempotency_key,
    )


class Fallback(str, Enum):
    """What a step does when it exhausts its retries — never a silent default."""

    DEGRADE = "degrade"  # READ_ONLY: cached value or surface the error to the model
    ESCALATE = "escalate"  # privileged: STOP and route to a human (request_approval)


_FALLBACK_BY_TIER: dict[RiskTier, Fallback] = {
    RiskTier.READ_ONLY: Fallback.DEGRADE,
    RiskTier.EXTERNAL_COMMS: Fallback.ESCALATE,
    RiskTier.REVERSIBLE_WRITE: Fallback.ESCALATE,
    RiskTier.IRREVERSIBLE_WRITE: Fallback.ESCALATE,
    RiskTier.MONEY_MOVEMENT: Fallback.ESCALATE,  # the one that must never "assume it worked"
}


def fallback_for(tool_name: str) -> Fallback:
    """The fallback for a failed step — a risk-tier decision, read from the frozen
    `TOOL_RISK`. Fails closed (`KeyError`) on an unknown tool; a failed money movement
    escalates to a human and never guesses."""
    return _FALLBACK_BY_TIER[TOOL_RISK[tool_name]]
