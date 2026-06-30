"""The deploy gauntlet — four stages, first failure stops the line.

These pin: a clean change promotes; an illegal tool path is blocked at stage 1
before anything else runs; a weak judge score blocks at stage 2; a significantly
worse run blocks at stage 3 (McNemar, Ch 21); a canary breach blocks at stage 4
(Ch 31); and the stages are *ordered* — a structural failure short-circuits before
the judge even scores. Reuses Ch 20/21/31; pure, no spend.
"""

from __future__ import annotations

from typing import Any

from ch20_structural.metrics import per_case_counts

from .deploy_gate import (
    CanaryResult,
    DeployStage,
    StatComparison,
    StructuralResult,
    run_deploy_gate,
)

_LEGAL_PATH = ("lookup_invoice", "match_to_po", "check_budget", "schedule_payment")
_CLEAN_CANARY = {
    "path_violation_rate": 0.0,
    "approval_override_rate": 0.05,
    "judge_score_p50_drop": 0.0,
    "schedule_payment_error_rate": 0.0,
}


def _inputs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "structural": StructuralResult(
            tool_counts=per_case_counts(expected=_LEGAL_PATH, actual=_LEGAL_PATH),
            idempotent=True,
            path_valid=True,
        ),
        "judge_score": 0.9,
        "stats": StatComparison(regressions=0, gains=3),
        "canary": CanaryResult(canary=_CLEAN_CANARY, control=_CLEAN_CANARY),
    }
    return base | overrides


def test_a_clean_change_promotes() -> None:
    decision = run_deploy_gate(**_inputs())
    assert decision.promoted
    assert decision.blocked_at is None


def test_an_illegal_path_blocks_at_stage_one() -> None:
    structural = StructuralResult(
        tool_counts=per_case_counts(expected=_LEGAL_PATH, actual=_LEGAL_PATH),
        idempotent=True,
        path_valid=False,  # paid before it matched, say
    )
    decision = run_deploy_gate(**_inputs(structural=structural))
    assert not decision.promoted
    assert decision.blocked_at is DeployStage.OFFLINE_STRUCTURAL


def test_a_non_idempotent_change_blocks_at_stage_one() -> None:
    structural = StructuralResult(
        tool_counts=per_case_counts(expected=_LEGAL_PATH, actual=_LEGAL_PATH),
        idempotent=False,  # a re-run would double-pay
        path_valid=True,
    )
    decision = run_deploy_gate(**_inputs(structural=structural))
    assert decision.blocked_at is DeployStage.OFFLINE_STRUCTURAL
    assert "idempotency" in decision.reason


def test_a_weak_judge_score_blocks_at_stage_two() -> None:
    decision = run_deploy_gate(**_inputs(judge_score=0.4))
    assert not decision.promoted
    assert decision.blocked_at is DeployStage.JUDGE


def test_a_significantly_worse_run_blocks_at_stage_three() -> None:
    # Ten cases regress, none gain — McNemar (Ch 21) says it's real, not noise.
    decision = run_deploy_gate(**_inputs(stats=StatComparison(regressions=10, gains=0)))
    assert not decision.promoted
    assert decision.blocked_at is DeployStage.STATISTICAL
    assert "McNemar" in decision.reason


def test_a_single_regression_is_noise_and_does_not_block() -> None:
    # One net flip proves nothing (Ch 21) — the gauntlet must not block on it.
    decision = run_deploy_gate(**_inputs(stats=StatComparison(regressions=1, gains=0)))
    assert decision.promoted


def test_a_canary_breach_blocks_at_stage_four() -> None:
    bad_canary = CanaryResult(
        canary={**_CLEAN_CANARY, "schedule_payment_error_rate": 0.01},
        control=_CLEAN_CANARY,
    )
    decision = run_deploy_gate(**_inputs(canary=bad_canary))
    assert not decision.promoted
    assert decision.blocked_at is DeployStage.CANARY


def test_the_stages_are_ordered_structural_short_circuits_the_judge() -> None:
    # Both stage 1 and stage 2 would fail; the earlier stage must be the one named.
    structural = StructuralResult(
        tool_counts=per_case_counts(expected=_LEGAL_PATH, actual=_LEGAL_PATH),
        idempotent=True,
        path_valid=False,
    )
    decision = run_deploy_gate(**_inputs(structural=structural, judge_score=0.0))
    assert decision.blocked_at is DeployStage.OFFLINE_STRUCTURAL
