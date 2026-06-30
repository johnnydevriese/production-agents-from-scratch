"""ch14 — a router is a classifier, so we score it like one.

Two kinds of test here. The `evaluate` tests run a deterministic stand-in router
over the golden set offline (no model, no spend) and check the harness records what
the router did. The metric tests hand-build `RoutingResult` lists directly — the
router is a black box, so the math doesn't need one — and pin the properties that
matter: recall on AP is the safety floor, and cost-weighted error punishes the
dangerous `(AP, REPORTING)` cell harder than a cheap mistake even when the raw
error *count* is identical.
"""

from __future__ import annotations

import pytest

from autopilot import RouteDecision, Specialist

from .golden_cases import GOLDEN_CASES
from .routing_eval import (
    BudgetExceeded,
    RoutingBudget,
    RoutingCase,
    RoutingResult,
    assert_within_budget,
    confidently_wrong,
    confusion_matrix,
    cost_weighted_error,
    evaluate,
    precision,
    recall,
)


class _GoldRouter:
    """Routes every request to its gold label — a perfect router, deterministic and
    offline. Lets us exercise `evaluate` without a model call."""

    def __init__(self, cases: list[RoutingCase]) -> None:
        self._answers = {c.request: c.gold for c in cases}

    def route(self, request: str) -> RouteDecision:
        return RouteDecision(
            specialist=self._answers[request], confidence=0.99, rationale="gold"
        )


class _BlindReportingRouter:
    """Reproduces the Chapter 13 bug: sends duplicate-charge complaints to REPORTING.
    Everything else it gets right."""

    def __init__(self, cases: list[RoutingCase]) -> None:
        self._answers = {c.request: c.gold for c in cases}

    def route(self, request: str) -> RouteDecision:
        if "billed twice" in request or "duplicate" in request:
            return RouteDecision(
                specialist=Specialist.REPORTING, confidence=0.9, rationale="blind"
            )
        return RouteDecision(
            specialist=self._answers[request], confidence=0.9, rationale="ok"
        )


def _result(
    gold: Specialist,
    predicted: Specialist,
    *,
    confidence: float = 0.9,
    latency_ms: float = 10.0,
) -> RoutingResult:
    return RoutingResult(
        case=RoutingCase(request="synthetic", gold=gold),
        predicted=predicted,
        confidence=confidence,
        latency_ms=latency_ms,
        correct=predicted == gold,
    )


def test_evaluate_records_predicted_and_correctness() -> None:
    results = evaluate(_GoldRouter(GOLDEN_CASES), GOLDEN_CASES)
    assert len(results) == len(GOLDEN_CASES)
    assert all(r.correct for r in results)  # the perfect router scores perfectly
    assert all(r.latency_ms >= 0.0 for r in results)  # every call was timed


def test_evaluate_repeats_runs_each_case_k_times() -> None:
    results = evaluate(_GoldRouter(GOLDEN_CASES), GOLDEN_CASES, repeats=3)
    assert len(results) == 3 * len(GOLDEN_CASES)


def test_evaluate_rejects_nonsense_repeats() -> None:
    with pytest.raises(ValueError, match="repeats must be >= 1"):
        evaluate(_GoldRouter(GOLDEN_CASES), GOLDEN_CASES, repeats=0)


def test_confusion_matrix_counts_the_dangerous_cell() -> None:
    results = evaluate(_BlindReportingRouter(GOLDEN_CASES), GOLDEN_CASES)
    matrix = confusion_matrix(results)
    # The Chapter 13 incident, quantified: AP requests landing in REPORTING.
    assert matrix[(Specialist.AP, Specialist.REPORTING)] == 2
    assert matrix[(Specialist.REPORTING, Specialist.REPORTING)] > 0  # diagonal intact


def test_recall_on_ap_is_the_safety_metric() -> None:
    results = evaluate(_BlindReportingRouter(GOLDEN_CASES), GOLDEN_CASES)
    # Two of the four AP cases were sent to REPORTING -> AP recall is 0.5.
    assert recall(results, Specialist.AP) == pytest.approx(0.5)
    assert recall(results, Specialist.RECONCILIATION) == pytest.approx(1.0)


def test_recall_raises_when_no_relevant_cases() -> None:
    results = [_result(Specialist.REPORTING, Specialist.REPORTING)]
    with pytest.raises(ValueError, match="no cases with gold=ap"):
        recall(results, Specialist.AP)


def test_precision_raises_when_label_never_predicted() -> None:
    results = [_result(Specialist.AP, Specialist.AP)]
    with pytest.raises(ValueError, match="no routes predicted reporting"):
        precision(results, Specialist.REPORTING)


def test_cost_weighted_error_respects_asymmetry() -> None:
    # Two routers, ONE error each. The counts are identical; the costs are not.
    dangerous = [_result(Specialist.AP, Specialist.REPORTING)]  # the Ch13 bug
    cheap = [_result(Specialist.REPORTING, Specialist.AP)]  # AP just declines
    assert cost_weighted_error(dangerous) == 10.0
    assert cost_weighted_error(cheap) == 1.0
    assert cost_weighted_error(dangerous) > cost_weighted_error(cheap)


def test_cost_weighted_error_is_zero_for_a_perfect_router() -> None:
    results = evaluate(_GoldRouter(GOLDEN_CASES), GOLDEN_CASES)
    assert cost_weighted_error(results) == 0.0


def test_confidently_wrong_flags_high_confidence_misroutes() -> None:
    results = [
        _result(Specialist.AP, Specialist.REPORTING, confidence=0.95),  # caught
        _result(Specialist.AP, Specialist.REPORTING, confidence=0.40),  # below floor
        _result(Specialist.AP, Specialist.AP, confidence=0.99),  # correct, ignored
    ]
    flagged = confidently_wrong(results, min_confidence=0.8)
    assert len(flagged) == 1
    assert flagged[0].confidence == pytest.approx(0.95)


def _passing_results() -> list[RoutingResult]:
    return [
        _result(Specialist.AP, Specialist.AP, latency_ms=20.0),
        _result(Specialist.AP, Specialist.AP, latency_ms=30.0),
        _result(Specialist.REPORTING, Specialist.REPORTING, latency_ms=25.0),
    ]


_BUDGET = RoutingBudget(p95_latency_ms=100.0, cost_per_1k_routes=5.0, min_recall_ap=0.9)


def test_budget_passes_a_fast_accurate_cheap_router() -> None:
    assert_within_budget(_passing_results(), _BUDGET, cost_per_1k_routes=2.0)


def test_budget_rejects_a_slow_router() -> None:
    slow = [_result(Specialist.AP, Specialist.AP, latency_ms=500.0)]
    with pytest.raises(BudgetExceeded, match="p95"):
        assert_within_budget(slow, _BUDGET, cost_per_1k_routes=2.0)


def test_budget_rejects_a_costly_router() -> None:
    with pytest.raises(BudgetExceeded, match="cost"):
        assert_within_budget(_passing_results(), _BUDGET, cost_per_1k_routes=9.0)


def test_budget_rejects_low_ap_recall() -> None:
    leaky = [
        _result(Specialist.AP, Specialist.REPORTING, latency_ms=10.0),
        _result(Specialist.AP, Specialist.AP, latency_ms=10.0),
    ]
    with pytest.raises(BudgetExceeded, match="AP recall"):
        assert_within_budget(leaky, _BUDGET, cost_per_1k_routes=2.0)
