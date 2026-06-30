"""Step ⑦ — the online monitors, and the risk-tier policy that drives them.

These pin the close of the loop: a double-pay (or an empty key) pages; a misroute is
caught but only trended, not paged; a clean run passes both. And the difference is
not hand-picked — `policy_for` derives the sample rate and paging from the failure's
risk tier, so the money-movement monitor is 100%/page and the quality signal is
sampled/no-page. Pure, no spend.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from autopilot import InvoiceId, Payment, RiskTier, Specialist

from .monitors import (
    MonitorTrace,
    money_movement_only_under_ap,
    pages_raised,
    payment_is_idempotent,
    policy_for,
    run_monitors,
)


def _payment(key: str) -> Payment:
    return Payment(
        invoice_id=InvoiceId("INV-1043"),
        amount=Decimal("2988.09"),
        idempotency_key=key,
        scheduled_for=date(2026, 7, 12),
    )


_CLEAN = MonitorTrace(
    route=Specialist.AP,
    tools_called=("match_to_po", "check_budget", "schedule_payment"),
    payments=(_payment("k-1043"),),
)
_DOUBLE_PAY = MonitorTrace(
    route=Specialist.REPORTING,
    tools_called=("check_budget", "schedule_payment", "schedule_payment"),
    payments=(_payment(""), _payment("")),
)


def test_a_double_pay_fails_idempotency_and_pages() -> None:
    result = payment_is_idempotent(_DOUBLE_PAY)
    assert not result.ok
    assert result.page  # money movement: a page, not a chart
    assert result.reason is not None and "2 payments" in result.reason


def test_an_empty_key_fails_idempotency_and_pages() -> None:
    one_unkeyed = MonitorTrace(
        route=Specialist.AP,
        tools_called=("schedule_payment",),
        payments=(_payment(""),),
    )
    result = payment_is_idempotent(one_unkeyed)
    assert not result.ok and result.page


def test_a_misroute_to_money_is_caught_but_not_paged() -> None:
    result = money_movement_only_under_ap(_DOUBLE_PAY)
    assert not result.ok  # schedule_payment fired outside the AP route
    assert not result.page  # a quality signal: trended, not paged


def test_a_clean_run_passes_both_monitors() -> None:
    results = run_monitors(_CLEAN)
    assert all(r.ok for r in results.values())


def test_only_the_money_monitor_pages_on_the_incident_shape() -> None:
    assert pages_raised(_DOUBLE_PAY) == ["payment_is_idempotent"]
    assert pages_raised(_CLEAN) == []


def test_the_policy_follows_the_risk_tier() -> None:
    money = policy_for(RiskTier.MONEY_MOVEMENT)
    assert money.sample_rate == 1.0 and money.pages  # check every one, page a human
    quality = policy_for(RiskTier.READ_ONLY)
    assert quality.sample_rate < 1.0 and not quality.pages  # sample and trend
