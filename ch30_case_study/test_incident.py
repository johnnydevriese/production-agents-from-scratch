"""Step ② — diagnose to the head of the causal chain, as a passing test.

These pin the discipline the chapter is built on: the double-pay the human saw is a
*symptom*; the root cause is the misroute, three links upstream. And of the three
defense-in-depth fixes, the most dangerous to drop is the *silent* one — the loud
double-pay is the safe failure. Pure, no spend.
"""

from __future__ import annotations

import pytest

from autopilot import RiskTier

from .incident import (
    DIAGNOSIS,
    FIXES,
    INCIDENT_1043,
    Bug,
    BugKind,
    most_dangerous_fix,
    root_cause,
    symptom,
)


def test_the_root_cause_is_the_misroute_not_the_double_pay() -> None:
    root = root_cause(DIAGNOSIS)
    assert root.order == 1
    assert "routed to the reporting specialist" in root.observation
    # The thing the human saw is the LAST link, and it is not what you fix.
    assert root is not symptom(DIAGNOSIS)


def test_the_double_pay_is_a_symptom_not_a_bug() -> None:
    seen = symptom(DIAGNOSIS)
    assert seen.kind is BugKind.SYMPTOM
    assert "second Payment" in seen.observation
    # Fixing only this leaves the silent variants — the chapter's whole warning.


def test_the_money_movement_bugs_carry_their_risk_tier() -> None:
    money = [b for b in DIAGNOSIS if b.tier is RiskTier.MONEY_MOVEMENT]
    # The two contributing bugs plus the symptom all touch the money-movement tool.
    assert {b.order for b in money} == {2, 3, 4}


def test_the_most_dangerous_fix_to_drop_is_the_silent_one() -> None:
    dangerous = most_dangerous_fix(FIXES)
    assert dangerous.silent_if_removed
    # The infrastructure (idempotency) fix is NOT it: removing it shows as a
    # double-pay a human inbox catches — loud, therefore safer.
    idempotency_fix = next(f for f in FIXES if f.layer == "infrastructure")
    assert not idempotency_fix.silent_if_removed


def test_defense_in_depth_has_more_than_one_layer() -> None:
    # Any single fix stops Tuesday; we ship all three, at three different layers.
    assert len({f.layer for f in FIXES}) == 3


def test_a_diagnosis_must_have_exactly_one_root_cause() -> None:
    two_roots = (
        Bug(order=1, observation="a", kind=BugKind.ROOT_CAUSE),
        Bug(order=2, observation="b", kind=BugKind.ROOT_CAUSE),
    )
    with pytest.raises(ValueError, match="exactly one root cause"):
        root_cause(two_roots)


def test_the_incident_timestamp_is_timezone_aware() -> None:
    # An incident without a real instant is not a record you can query (Ch 18).
    assert INCIDENT_1043.occurred_at.tzinfo is not None
