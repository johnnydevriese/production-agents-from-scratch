"""Step ⑦ — close the loop where the inputs are real.

The offline case (steps ④–⑥) proves the bug is gone *from the dataset we have*. It
says nothing about the inputs nobody imagined — and the incident exists *because*
production produced one. So the loop does not close until an online check watches
for the *shape* of this failure in live traffic.

Two monitors, deliberately different, and the difference *is* the lesson: a second
`schedule_payment` is an irreversible money event, sampled at 100% and **pages** a
human; a misroute is a quality signal, sampled and trended, not paged. The setting
is not hand-picked — it falls out of the risk taxonomy (`TOOL_RISK`, Chapter 3):
`policy_for` maps the failure's tier to its sample rate and paging, so the same
taxonomy that decides *what needs confirmation* decides *what needs a page*.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from autopilot import Payment, RiskTier, Specialist


class MonitorTrace(BaseModel, frozen=True):
    """The live-traffic projection a monitor reads: where it routed, the tool path,
    and the payments it emitted. The online analog of the offline `IncidentRun`."""

    route: Specialist
    tools_called: tuple[str, ...] = ()
    payments: tuple[Payment, ...] = ()


class CheckResult(BaseModel, frozen=True):
    """One monitor's verdict on one trace."""

    ok: bool
    reason: str | None = None
    page: bool = False

    @classmethod
    def passed(cls) -> CheckResult:
        return cls(ok=True)

    @classmethod
    def fail(cls, reason: str, *, page: bool = False) -> CheckResult:
        return cls(ok=False, reason=reason, page=page)


def payment_is_idempotent(trace: MonitorTrace) -> CheckResult:
    """Money movement: a run must pay at most once, always with a non-empty key."""
    pays = [tool for tool in trace.tools_called if tool == "schedule_payment"]
    if len(pays) > 1:
        return CheckResult.fail(f"{len(pays)} payments in one run", page=True)
    if any(not p.idempotency_key for p in trace.payments):
        return CheckResult.fail("payment with empty idempotency_key", page=True)
    return CheckResult.passed()


def money_movement_only_under_ap(trace: MonitorTrace) -> CheckResult:
    """Routing drift: schedule_payment must never fire outside the AP route."""
    if trace.route is not Specialist.AP and "schedule_payment" in trace.tools_called:
        return CheckResult.fail("schedule_payment outside the AP route")
    return CheckResult.passed()


class MonitorPolicy(BaseModel, frozen=True):
    """How aggressively a monitor watches — derived from the failure's risk tier."""

    sample_rate: float
    pages: bool


# Data-driven, not an if/elif chain: the failure's risk tier → how we watch it.
# Money movement and irreversible writes are checked on every trace and page; a
# lower-severity quality signal is sampled and trended.
_POLICY_BY_TIER: dict[RiskTier, MonitorPolicy] = {
    RiskTier.MONEY_MOVEMENT: MonitorPolicy(sample_rate=1.0, pages=True),
    RiskTier.IRREVERSIBLE_WRITE: MonitorPolicy(sample_rate=1.0, pages=True),
}
_QUALITY_SIGNAL_POLICY = MonitorPolicy(sample_rate=0.1, pages=False)


def policy_for(tier: RiskTier) -> MonitorPolicy:
    """Sample rate and paging as a function of the risk tier the monitor guards."""
    return _POLICY_BY_TIER.get(tier, _QUALITY_SIGNAL_POLICY)


# Each monitor declares the tier of the failure it catches, so its policy is read
# from the taxonomy rather than hand-tuned. payment_is_idempotent guards a money
# event; the routing-drift monitor guards a quality signal.
MONITORS: dict[str, tuple[Callable[[MonitorTrace], CheckResult], RiskTier]] = {
    "payment_is_idempotent": (payment_is_idempotent, RiskTier.MONEY_MOVEMENT),
    "money_movement_only_under_ap": (money_movement_only_under_ap, RiskTier.READ_ONLY),
}


def run_monitors(trace: MonitorTrace) -> dict[str, CheckResult]:
    """Run every monitor on one trace; return each verdict by name."""
    return {name: check(trace) for name, (check, _tier) in MONITORS.items()}


def pages_raised(trace: MonitorTrace) -> list[str]:
    """Monitors that both failed *and* are allowed to page (their tier opts in)."""
    return [
        name
        for name, (check, tier) in MONITORS.items()
        if not check(trace).ok and policy_for(tier).pages
    ]
