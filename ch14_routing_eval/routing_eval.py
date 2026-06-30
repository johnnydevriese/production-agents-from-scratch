"""An evaluation harness for the router — because a router is a classifier.

The router keeps its frozen `Router.route(request) -> RouteDecision` interface from
Chapter 13; this harness wraps it and knows the ground truth. It scores the router
the way classifiers have been scored since before LLMs: a confusion matrix, per-
class precision/recall, a cost-weighted error that respects the asymmetry (a
duplicate-charge misroute costs far more than a misrouted trends question), and a
latency/cost budget enforced as a hard gate.

Everything here is pure code over recorded results — no model call, no spend. The
router under test is a black box; the harness is what makes it measurable.
"""

from __future__ import annotations

import math
import time
from collections import Counter
from collections.abc import Sequence

from pydantic import BaseModel, Field

from autopilot import Router, Specialist


class RoutingCase(BaseModel):
    request: str
    gold: Specialist  # the route this request SHOULD get
    note: str = ""  # provenance: which incident/ticket this case guards (Ch 24)


class RoutingResult(BaseModel):
    case: RoutingCase
    predicted: Specialist
    confidence: float = Field(ge=0.0, le=1.0)
    latency_ms: float  # measured per call; this is what feeds the p95
    correct: bool


def evaluate(
    router: Router, cases: Sequence[RoutingCase], *, repeats: int = 1
) -> list[RoutingResult]:
    """Run each case through the router, timing every call.

    The router is a random variable (Chapter 1): a single pass is a *sample*, not an
    answer. `repeats > 1` runs each case k times so the caller can report a rate with
    an interval (Chapter 21) instead of trusting one draw.
    """
    if repeats < 1:
        raise ValueError(f"repeats must be >= 1, got {repeats}")
    results: list[RoutingResult] = []
    for case in cases:
        for _ in range(repeats):
            start = time.perf_counter()
            decision = router.route(case.request)  # the black box
            latency_ms = (time.perf_counter() - start) * 1_000
            results.append(
                RoutingResult(
                    case=case,
                    predicted=decision.specialist,
                    confidence=decision.confidence,
                    latency_ms=latency_ms,
                    correct=decision.specialist
                    == case.gold,  # path correctness, full stop
                )
            )
    return results


def confusion_matrix(
    results: Sequence[RoutingResult],
) -> Counter[tuple[Specialist, Specialist]]:
    """`(gold, predicted) -> count`. The off-diagonal cells are your ranked bug list;
    `(AP, REPORTING)` is the Chapter 13 duplicate-charge bug, quantified."""
    return Counter((r.case.gold, r.predicted) for r in results)


def recall(results: Sequence[RoutingResult], label: Specialist) -> float:
    """Of requests that *should* reach `label`, how many did. Recall on AP is the
    safety floor: a miss is a payment question that never reached the agent that pays."""
    relevant = [r for r in results if r.case.gold == label]
    if not relevant:
        raise ValueError(f"no cases with gold={label.value}")
    return sum(r.correct for r in relevant) / len(relevant)


def precision(results: Sequence[RoutingResult], label: Specialist) -> float:
    """Of requests routed *to* `label`, how many belonged."""
    predicted = [r for r in results if r.predicted == label]
    if not predicted:
        raise ValueError(f"no routes predicted {label.value}")
    return sum(r.case.gold == label for r in predicted) / len(predicted)


# Cost of routing a (gold -> predicted) pair wrong. The diagonal is 0 (correct);
# unspecified pairs default to a flat 1.0. Data-driven, not an if/elif chain.
MISROUTE_COST: dict[tuple[Specialist, Specialist], float] = {
    (Specialist.AP, Specialist.REPORTING): 10.0,  # duplicate-charge blind spot: worst
    (Specialist.AP, Specialist.RECONCILIATION): 4.0,
    (Specialist.REPORTING, Specialist.AP): 1.0,  # cheap: AP declines, no money moves
    (Specialist.VENDOR_MGMT, Specialist.AP): 3.0,
}
_DEFAULT_MISROUTE_COST = 1.0


def cost_weighted_error(results: Sequence[RoutingResult]) -> float:
    """Total cost of the mistakes — not their count. The only metric that respects
    the asymmetry: two routers with identical accuracy can differ wildly here."""
    return sum(
        MISROUTE_COST.get((r.case.gold, r.predicted), _DEFAULT_MISROUTE_COST)
        for r in results
        if not r.correct
    )


def confidently_wrong(
    results: Sequence[RoutingResult], *, min_confidence: float = 0.8
) -> list[RoutingResult]:
    """The subtle failure mode: high confidence, wrong label. The re-routing guard
    fires on *low* confidence, so a confidently-wrong route sails straight through.
    You can only catch it by checking confidence against the gold label."""
    return [r for r in results if not r.correct and r.confidence >= min_confidence]


def _percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        raise ValueError("cannot take a percentile of no values")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100) * (len(ordered) - 1)
    low, high = math.floor(rank), math.ceil(rank)
    if low == high:
        return ordered[low]
    frac = rank - low
    return ordered[low] * (1 - frac) + ordered[high] * frac


class RoutingBudget(BaseModel):
    p95_latency_ms: float  # hard ceiling on the slow tail
    cost_per_1k_routes: float  # what we'll pay to route a thousand requests
    min_recall_ap: float = Field(ge=0.0, le=1.0)  # safety floor: never lose AP


class BudgetExceeded(Exception):
    """The router missed a budget dimension. Raise, never warn-and-pass — a budget
    you don't enforce is a comment."""


def assert_within_budget(
    results: Sequence[RoutingResult],
    budget: RoutingBudget,
    *,
    cost_per_1k_routes: float,
) -> None:
    """Enforce the budget like a test. Latency and recall are measured here; the
    dollar cost is metered by the provider (Chapter 28) and passed in."""
    p95 = _percentile([r.latency_ms for r in results], 95)
    if p95 > budget.p95_latency_ms:
        raise BudgetExceeded(f"p95 {p95:.0f}ms > {budget.p95_latency_ms:.0f}ms")
    if cost_per_1k_routes > budget.cost_per_1k_routes:
        raise BudgetExceeded(
            f"cost ${cost_per_1k_routes:.2f}/1k > ${budget.cost_per_1k_routes:.2f}/1k"
        )
    ap_recall = recall(results, Specialist.AP)
    if ap_recall < budget.min_recall_ap:
        raise BudgetExceeded(f"AP recall {ap_recall:.2f} < {budget.min_recall_ap:.2f}")
