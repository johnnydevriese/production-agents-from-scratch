"""Steps ④–⑥ — the incident as a regression case over the REAL agent's span tree.

These pin the TDD core: the buggy run reproduces all four diagnosed failures; the
fixed run clears all four; and the `paid_exactly_once` check is Chapter 20's real
`ToolCallCount` over a tree captured from the actual Chapter 11 autopilot — so a red
is proof the *agent* double-paid, not a fixture. The "silent variant" test is the
chapter's sharpest point made executable: drop the routing/scoping fix and the loud
double-pay disappears while the real defect (the wrong agent pays) survives.

Smoke lane: every case is a live LLM round trip, offline via `FunctionModel`.
"""

from __future__ import annotations

import pytest

from autopilot import Specialist
from ch12_multiagent.specialists import TOOLS_BY_SPECIALIST

from .regression import buggy_run, check_incident, fixed_run, silent_variant_run

pytestmark = [pytest.mark.span_eval, pytest.mark.eval_smoke]


def test_the_buggy_run_reproduces_all_four_failures() -> None:
    report = check_incident(buggy_run())
    assert not report.passed
    assert set(report.failures) == {
        "routed_to_ap",
        "money_movement_only_under_ap",
        "paid_exactly_once",
        "payment_has_idempotency_key",
    }


def test_the_fixed_run_clears_every_check() -> None:
    report = check_incident(fixed_run())
    assert report.passed
    assert report.failures == []


def test_paid_exactly_once_is_chapter_20s_real_count_over_the_real_agent() -> None:
    # The buggy model emitted schedule_payment twice; the real loop dispatched both,
    # and ToolCallCount("schedule_payment", 1) reads "got 2" off the captured tree.
    assert check_incident(buggy_run()).paid_exactly_once is False
    assert check_incident(fixed_run()).paid_exactly_once is True


def test_the_silent_variant_loses_the_loud_symptom_but_keeps_the_real_defect() -> None:
    report = check_incident(silent_variant_run())
    # The double-pay is GONE — no human inbox catches anything…
    assert report.paid_exactly_once is True
    assert report.payment_has_idempotency_key is True
    # …but the wrong agent still pays. Only the scoping check sees it.
    assert report.money_movement_only_under_ap is False
    assert report.routed_to_ap is False
    assert report.failures == ["routed_to_ap", "money_movement_only_under_ap"]


def test_the_scoping_fix_removes_money_movement_from_the_reporting_menu() -> None:
    # Bug ② as a structural fact (Chapter 12): schedule_payment lives in the AP row
    # alone. Strip it from the reporting menu and a misroute cannot reach money.
    ap_menu = {tool.__name__ for tool in TOOLS_BY_SPECIALIST[Specialist.AP]}
    reporting_menu = {
        tool.__name__ for tool in TOOLS_BY_SPECIALIST[Specialist.REPORTING]
    }
    assert "schedule_payment" in ap_menu
    assert "schedule_payment" not in reporting_menu
