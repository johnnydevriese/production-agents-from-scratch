"""Discipline 1 — the on-call playbook, anchored on the trace, not the log.

The 2 a.m. page says "payments stuck." The worst move is to start reading code: the
agent is a distributed, probabilistic system, and only the trace knows what actually
happened. So the playbook is fixed — stabilize, then read one bad trace, then
*classify*, then (only then) hypothesize.

Step 3 is what turns panic into routine. Because the action space is a bounded menu
of typed tools, a production failure is almost always one of a small, enumerable set,
and the trace tells you which. That classification is a data table, not an if/elif
chain — the bounded menu is what makes a *playbook* possible at all.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from pydantic import BaseModel

from autopilot import TOOL_RISK, RiskTier

# The kill switch is for the only irreversible tier — money movement.
_STABILIZE_TIERS = frozenset({RiskTier.MONEY_MOVEMENT})


class FailureClass(str, Enum):
    """The small, enumerable set a bounded-action agent fails into."""

    INTEGRATION_DOWN = "integration_down"
    WORLD_MOVED = "world_moved"
    MODEL_REGRESSION = "model_regression"
    DRIFT = "drift"
    NOVEL = "novel"


class TraceSymptoms(BaseModel, frozen=True):
    """What reading one bad trace (step 2) surfaces — the inputs to classification."""

    integration_error: bool = False  # a tool span threw or timed out
    path_diverged: bool = (
        False  # wrong tool path: skipped check_budget, paid an EXCEPTION
    )
    data_anomaly: bool = (
        False  # path is green but the data is wrong (new account, cents)
    )
    aggregate_only: bool = False  # no single bad trace; only the aggregate metric moved


# Priority-ordered, read top-down like the playbook table: the first symptom that
# matches names the class. Data-driven — adding a class is one row.
_CLASSIFIERS: tuple[tuple[FailureClass, Callable[[TraceSymptoms], bool]], ...] = (
    (FailureClass.INTEGRATION_DOWN, lambda s: s.integration_error),
    (FailureClass.MODEL_REGRESSION, lambda s: s.path_diverged),
    (FailureClass.WORLD_MOVED, lambda s: s.data_anomaly),
    (FailureClass.DRIFT, lambda s: s.aggregate_only),
)

_RESPONDER: dict[FailureClass, str] = {
    FailureClass.INTEGRATION_DOWN: "platform on-call",
    FailureClass.WORLD_MOVED: "you + an AP analyst",
    FailureClass.MODEL_REGRESSION: "you",
    FailureClass.DRIFT: "you, during business hours",
    FailureClass.NOVEL: "escalate; this becomes the next case study (Ch 30)",
}


def classify_failure(symptoms: TraceSymptoms) -> FailureClass:
    """Name the failure class from what the trace shows. Unmatched ⇒ NOVEL — which is
    not a defeat but the seed of the next case study."""
    for failure_class, matches in _CLASSIFIERS:
        if matches(symptoms):
            return failure_class
    return FailureClass.NOVEL


def responder_for(failure_class: FailureClass) -> str:
    """Who to wake up. The class tells you, so you don't page everyone at 2 a.m."""
    return _RESPONDER[failure_class]


def should_flip_kill_switch(*, misfiring_tool: str | None) -> bool:
    """Step 0 — stabilize FIRST, diagnose SECOND. Flip the kill switch only when a
    money-movement tool is mis-firing: it's the one irreversible tier, so the trade
    (throughput for safety) is always worth it there and nowhere else."""
    if misfiring_tool is None:
        return False
    return TOOL_RISK.get(misfiring_tool) in _STABILIZE_TIERS
