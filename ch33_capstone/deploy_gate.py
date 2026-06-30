"""The deploy gauntlet — how a change ships without losing money on Wednesday.

A proposed change (new prompt, new model, retrained router) runs four stages in
order, and the first one it fails stops the line. Nothing here is new; it is the
book's eval apparatus, *assembled* into a single decision:

    1. OFFLINE STRUCTURAL EVAL (Ch 20) — tool F1, idempotency, path validity
    2. LLM-AS-JUDGE on answer quality (Ch 22) — scored, calibrated
    3. STATISTICAL GATE (Ch 21) — McNemar vs. the current prod version
    4. CANARY (Ch 31) — a live slice vs. a parallel control arm

Stage 3 exists because an LLM call is a random variable even at temperature 0
(Chapter 1): "the candidate scored better" is meaningless until "…and the
difference beats run-to-run noise." The structural and money-path gates are
*zero-tolerance* — they are the **path**, not the **answer**.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from pydantic import BaseModel

from ch20_structural.metrics import ToolCounts, f1
from ch21_stats.compare import paired_eval_test
from ch31_operating.canary import canary_breaches


class DeployStage(str, Enum):
    """The gauntlet, in order. `PROMOTED` is the terminal pass state."""

    OFFLINE_STRUCTURAL = "offline_structural"
    JUDGE = "judge"
    STATISTICAL = "statistical"
    CANARY = "canary"
    PROMOTED = "promoted"


class StructuralResult(BaseModel, frozen=True):
    """Stage 1 inputs — the Chapter 20 offline structural eval, as data."""

    tool_counts: ToolCounts  # precision/recall/F1 over the tool path
    idempotent: bool  # the idempotency structural eval (Ch 20 / Ch 26)
    path_valid: bool  # legal tool sequence: matched before paid, etc.


class StatComparison(BaseModel, frozen=True):
    """Stage 3 inputs — paired pass/fail flips vs. the current prod version."""

    regressions: int  # cases that flipped pass → fail against prod
    gains: int  # cases that flipped fail → pass against prod


class CanaryResult(BaseModel, frozen=True):
    """Stage 4 inputs — the canary arm's online metrics vs. the control arm."""

    canary: dict[str, float]
    control: dict[str, float]


class DeployDecision(BaseModel, frozen=True):
    """The verdict. `blocked_at` is `None` exactly when `promoted` is True."""

    promoted: bool
    blocked_at: DeployStage | None
    reason: str


def _structural_failure(*, structural: StructuralResult, min_f1: float) -> str | None:
    if not structural.path_valid:
        return "path validity failed: an illegal tool sequence (Ch 20)"
    if not structural.idempotent:
        return "idempotency eval failed: a re-run would double-pay (Ch 20/26)"
    score = f1(structural.tool_counts)
    if score < min_f1:
        return f"tool F1 {score:.2f} below threshold {min_f1:.2f} (Ch 20)"
    return None


def _statistical_failure(*, stats: StatComparison) -> str | None:
    """McNemar (Ch 21) on the paired outcomes. A migration that is *significantly*
    worse than prod — more regressions than gains, beyond noise — does not ship."""
    p_value = paired_eval_test(pass_to_fail=stats.regressions, fail_to_pass=stats.gains)
    if p_value < 0.05 and stats.regressions > stats.gains:
        return f"significantly worse than prod (McNemar p={p_value:.3f}, Ch 21)"
    return None


def run_deploy_gate(
    *,
    structural: StructuralResult,
    judge_score: float,
    stats: StatComparison,
    canary: CanaryResult,
    min_f1: float = 0.9,
    min_judge: float = 0.7,
) -> DeployDecision:
    """Run the four stages in order; the first failure stops the line.

    The checks are an ordered table, not an if/elif ladder — each yields a reason
    string when it blocks, or `None` to fall through to the next stage.
    """
    checks: tuple[tuple[DeployStage, Callable[[], str | None]], ...] = (
        (
            DeployStage.OFFLINE_STRUCTURAL,
            lambda: _structural_failure(structural=structural, min_f1=min_f1),
        ),
        (
            DeployStage.JUDGE,
            lambda: (
                f"judge score {judge_score:.2f} below {min_judge:.2f} (Ch 22)"
                if judge_score < min_judge
                else None
            ),
        ),
        (DeployStage.STATISTICAL, lambda: _statistical_failure(stats=stats)),
        (
            DeployStage.CANARY,
            lambda: (
                f"canary breached: {breaches} (Ch 31)"
                if (
                    breaches := canary_breaches(
                        canary=canary.canary, control=canary.control
                    )
                )
                else None
            ),
        ),
    )
    for stage, check in checks:
        reason = check()
        if reason is not None:
            return DeployDecision(promoted=False, blocked_at=stage, reason=reason)
    return DeployDecision(
        promoted=True, blocked_at=None, reason="all four gates cleared"
    )
