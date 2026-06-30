"""Stage 4 — judge the path, and let McNemar decide, not the gap in means.

These pin the chapter's stage-4 disciplines: macro-F1 exposes the rare-class blind
spot that aggregate accuracy hides; a single net flip between two routers is never
significant; a consistent run of gains is; and the head-to-head refuses misaligned
cases. Pure code over recorded results — reuses Ch 14 metrics and Ch 21's test.
"""

from __future__ import annotations

import pytest

from autopilot import Specialist
from ch14_routing_eval.routing_eval import RoutingCase, RoutingResult

from .evaluate import accuracy, head_to_head, macro_f1


def _result(
    request: str, gold: Specialist, predicted: Specialist, *, confidence: float = 0.9
) -> RoutingResult:
    return RoutingResult(
        case=RoutingCase(request=request, gold=gold),
        predicted=predicted,
        confidence=confidence,
        latency_ms=1.0,
        correct=predicted == gold,
    )


def _always_ap_on_imbalanced() -> list[RoutingResult]:
    # 8 AP, 1 REPORTING, 1 VENDOR_MGMT — a router that always says AP.
    ap = [_result(f"pay {i}", Specialist.AP, Specialist.AP) for i in range(8)]
    rep = [_result("trend", Specialist.REPORTING, Specialist.AP)]
    vm = [_result("onboard", Specialist.VENDOR_MGMT, Specialist.AP)]
    return ap + rep + vm


def test_macro_f1_exposes_the_blind_spot_aggregate_accuracy_hides() -> None:
    results = _always_ap_on_imbalanced()
    # The always-AP router looks fine on accuracy but is wrecked on macro-F1,
    # because it scores zero on the two classes it never predicts.
    assert accuracy(results) == pytest.approx(0.8)
    assert macro_f1(results) < accuracy(results)
    assert macro_f1(results) < 0.4


def test_two_identical_routers_show_no_significant_difference() -> None:
    cases = [
        _result("pay it", Specialist.AP, Specialist.AP),
        _result("trend", Specialist.REPORTING, Specialist.REPORTING),
    ]
    verdict = head_to_head(baseline=cases, candidate=cases)
    assert verdict.regressions == 0
    assert verdict.gains == 0
    assert verdict.mcnemar_p_value == 1.0
    assert not verdict.significant


def test_a_single_net_flip_is_not_significant() -> None:
    # One disagreement is noise — the chapter's "a one-point gap is noise" lesson.
    baseline = [_result("pay it", Specialist.AP, Specialist.REPORTING)]  # wrong
    candidate = [_result("pay it", Specialist.AP, Specialist.AP)]  # right
    verdict = head_to_head(baseline=baseline, candidate=candidate)
    assert (verdict.regressions, verdict.gains) == (0, 1)
    assert not verdict.significant


def test_a_consistent_run_of_gains_is_significant() -> None:
    # 10 cases the baseline misroutes and the candidate gets right: a real win.
    baseline = [
        _result(f"pay {i}", Specialist.AP, Specialist.REPORTING) for i in range(10)
    ]
    candidate = [_result(f"pay {i}", Specialist.AP, Specialist.AP) for i in range(10)]
    verdict = head_to_head(baseline=baseline, candidate=candidate)

    assert (verdict.regressions, verdict.gains) == (0, 10)
    assert verdict.significant
    assert verdict.candidate_ap_recall == pytest.approx(1.0)
    assert verdict.baseline_ap_recall == pytest.approx(0.0)


def test_the_head_to_head_refuses_misaligned_cases() -> None:
    baseline = [_result("pay it", Specialist.AP, Specialist.AP)]
    candidate = [_result("something else", Specialist.AP, Specialist.AP)]
    with pytest.raises(ValueError, match="aligned case-for-case"):
        head_to_head(baseline=baseline, candidate=candidate)
