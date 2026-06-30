"""The incident and its diagnosis, frozen as data — step ② of the loop.

A junior responder fixes the thing they see last (the double `schedule_payment`)
and calls it closed. The case-study method demands tracing the *causal chain* to
its head: the double-pay is a **symptom**, not the root cause. Modelling the
diagnosis as an ordered chain makes that discipline a passing test rather than a
good intention — `root_cause` is the misroute, never the symptom the human saw.

The fixes carry a `silent_if_removed` flag because of the chapter's sharpest
point: of three defense-in-depth fixes, the *most dangerous* to drop is not the
loud one (a double-pay a human inbox catches) but the silent one (the wrong agent
pays correctly-once, and no one notices).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from autopilot import RiskTier


class BugKind(str, Enum):
    """Where a finding sits in the causal chain. Only one bug is the head."""

    ROOT_CAUSE = "root_cause"  # the defect that started the chain
    CONTRIBUTING = "contributing"  # a real bug, but downstream of the root
    SYMPTOM = "symptom"  # what the human saw — a consequence, not a bug


class Bug(BaseModel, frozen=True):
    """One finding from reading the trace top-down, with its place in the chain."""

    order: int = Field(ge=1)  # position in the causal chain, 1 = head
    observation: str
    kind: BugKind
    tier: RiskTier | None = None  # the risk tier of the tool involved, if any


class Fix(BaseModel, frozen=True):
    """One layer of the defense-in-depth repair. Any single fix stops Tuesday's
    double-pay; we ship all three because each closes the hole at a different layer."""

    bug_order: int = Field(ge=1)  # the Bug this fix addresses
    layer: str  # infrastructure / architecture / routing
    change: str
    silent_if_removed: bool  # True ⇒ removing it fails with no human-visible signal


class Incident(BaseModel, frozen=True):
    """A signal converted into a record — the raw material the loop refines."""

    id: str
    request: str
    invoice_id: str
    signal: str  # the human report, verbatim and lossy
    occurred_at: datetime


INCIDENT_1043 = Incident(
    id="incident-2026-06-23-double-pay",
    request="Please pay invoice #1043 from Acme.",
    invoice_id="INV-1043",
    signal="Did invoice #1043 get paid twice? Two confirmations, eight minutes apart.",
    occurred_at=datetime(2026, 6, 23, 9, 14, tzinfo=timezone.utc),
)

# The diagnosis, read top-down off the span tree. Order matters: the misroute (1)
# put the request in front of an agent that should not have been able to pay (2);
# that agent's payment path never got the idempotency wiring (3); so a normal
# transient retry double-paid (4).
DIAGNOSIS: tuple[Bug, ...] = (
    Bug(
        order=1,
        observation="a payment intent routed to the reporting specialist",
        kind=BugKind.ROOT_CAUSE,
    ),
    Bug(
        order=2,
        observation="the reporting agent could reach schedule_payment at all",
        kind=BugKind.CONTRIBUTING,
        tier=RiskTier.MONEY_MOVEMENT,
    ),
    Bug(
        order=3,
        observation="schedule_payment ran with an empty idempotency_key",
        kind=BugKind.CONTRIBUTING,
        tier=RiskTier.MONEY_MOVEMENT,
    ),
    Bug(
        order=4,
        observation="the retry emitted a second Payment",
        kind=BugKind.SYMPTOM,
        tier=RiskTier.MONEY_MOVEMENT,
    ),
)

FIXES: tuple[Fix, ...] = (
    Fix(
        bug_order=3,
        layer="infrastructure",
        change="thread a deterministic idempotency_key on every payment path",
        silent_if_removed=False,  # its absence shows as a double-pay a human catches
    ),
    Fix(
        bug_order=2,
        layer="architecture",
        change="remove schedule_payment from the reporting agent's tool menu",
        silent_if_removed=True,  # the wrong agent pays correctly-once — no signal
    ),
    Fix(
        bug_order=1,
        layer="routing",
        change="add the misrouted example to the router's eval and training sets",
        silent_if_removed=True,  # the misroute alone pays correctly-once — no signal
    ),
)


def root_cause(diagnosis: tuple[Bug, ...]) -> Bug:
    """The head of the causal chain — the bug to fix first, not the one seen last."""
    roots = [bug for bug in diagnosis if bug.kind is BugKind.ROOT_CAUSE]
    if len(roots) != 1:
        raise ValueError(f"a diagnosis has exactly one root cause, found {len(roots)}")
    return roots[0]


def symptom(diagnosis: tuple[Bug, ...]) -> Bug:
    """What the human reported — the consequence, never the thing you fix."""
    symptoms = [bug for bug in diagnosis if bug.kind is BugKind.SYMPTOM]
    if not symptoms:
        raise ValueError("a diagnosis with no symptom did not start from a signal")
    return symptoms[-1]


def most_dangerous_fix(fixes: tuple[Fix, ...]) -> Fix:
    """The fix whose removal is *silent* — correct-once, no human-visible double-pay.
    The loud bug (the double-pay) is the safe one; the silent variant is the trap."""
    silent = [fix for fix in fixes if fix.silent_if_removed]
    if not silent:
        raise ValueError(
            "defense-in-depth with no silent layer is a single point of failure"
        )
    return silent[0]
