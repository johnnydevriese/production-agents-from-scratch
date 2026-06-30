"""ch22 — the judge, its bias mitigation, and its calibration, all offline.

A judge is a model call, so in production it costs tokens. Here every test injects
a `FunctionModel` (zero spend, deterministic) — the same discipline as every other
framework checkpoint. We are not testing whether a frontier model grades well; we
are testing the *machinery around it*: that the verdict is structured the way the
chapter requires, that the matcher's findings reach the prompt, that the pairwise
swap neutralizes position bias and costs exactly two calls, and that calibration
is chance-corrected and ordinal-aware.
"""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from autopilot import ApprovalRequest, InvoiceId, MatchResult

from .calibrate import calibrate
from .pairwise import PairVerdict, build_pairwise_judge, pairwise_winner
from .reason_judge import Grade, Verdict, build_reason_judge, judge_reason

_GOOD_REASON = "PO-3310 ordered 50 actuators; invoice bills 60. Hold for procurement."
_BAD_REASON = "This invoice requires manual review based on the analysis performed."
_FINDINGS = ["PO-3310 ordered 50 actuators; invoice bills 60 — quantity mismatch"]


def _user_text(messages: list[ModelMessage]) -> str:
    chunks = [
        part.content
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart) and isinstance(part.content, str)
    ]
    return "\n".join(chunks)


def _emitting_verdict(
    verdict: Verdict, *, seen: list[str] | None = None
) -> FunctionModel:
    def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if seen is not None:
            seen.append(_user_text(messages))
        out = (info.output_tools or [])[0].name
        return ModelResponse(
            parts=[ToolCallPart(tool_name=out, args=verdict.model_dump(mode="json"))]
        )

    return FunctionModel(model_fn)


def _approval(invoice_id: str, reason: str) -> ApprovalRequest:
    return ApprovalRequest(invoice_id=InvoiceId(invoice_id), reason=reason)


def _match(invoice_id: str) -> MatchResult:
    return MatchResult(
        invoice_id=InvoiceId(invoice_id), matched=False, discrepancies=_FINDINGS
    )


def test_garbage_reason_grades_unusable() -> None:
    verdict = Verdict(
        evidence_quote="requires manual review based on the analysis performed",
        reasoning="True but content-free; names no discrepancy and no action.",
        grade=Grade.UNUSABLE,
    )
    judge = build_reason_judge("anthropic:claude-sonnet-4-6")
    with judge.override(model=_emitting_verdict(verdict)):
        out = judge_reason(
            _approval("INV-7741", _BAD_REASON), _match("INV-7741"), judge=judge
        )
    assert out.grade is Grade.UNUSABLE


def test_good_reason_grades_good() -> None:
    verdict = Verdict(
        evidence_quote="PO-3310 ordered 50 actuators; invoice bills 60.",
        reasoning="Names the exact discrepancy and the next step; an approver can act.",
        grade=Grade.GOOD,
    )
    judge = build_reason_judge("anthropic:claude-sonnet-4-6")
    with judge.override(model=_emitting_verdict(verdict)):
        out = judge_reason(
            _approval("INV-7742", _GOOD_REASON), _match("INV-7742"), judge=judge
        )
    assert out.grade is Grade.GOOD


def test_verdict_puts_evidence_and_reasoning_before_the_grade() -> None:
    # Field order is the design, not cosmetics: the model generates left-to-right,
    # so the grade is conditioned on a quote and a rationale that already exist.
    assert tuple(Verdict.model_fields) == ("evidence_quote", "reasoning", "grade")


def test_judge_is_handed_the_matchers_findings() -> None:
    # The faithfulness anchor: feed the judge what the path actually found, or it
    # grades plausibility and hands a 4 to a confident, specific fabrication.
    seen: list[str] = []
    verdict = Verdict(evidence_quote="x", reasoning="y", grade=Grade.UNUSABLE)
    judge = build_reason_judge("anthropic:claude-sonnet-4-6")
    with judge.override(model=_emitting_verdict(verdict, seen=seen)):
        judge_reason(
            _approval("INV-7741", _BAD_REASON), _match("INV-7741"), judge=judge
        )
    prompt = seen[0]
    assert _FINDINGS[0] in prompt
    assert _BAD_REASON in prompt


# --- pairwise: position bias is mechanical, so its mitigation is too -------------


def _content_aware_pair_judge(*, calls: list[int] | None = None) -> FunctionModel:
    """A judge that prefers the reason naming 'procurement' wherever it appears —
    an *unbiased* judge whose pick tracks content, not slot."""

    def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if calls is not None:
            calls.append(1)
        text = _user_text(messages)
        second_at = text.index("Second reason:")
        winner: Literal["first", "second"] = (
            "first" if text.index("procurement") < second_at else "second"
        )
        out = (info.output_tools or [])[0].name
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=out,
                    args={"reasoning": "names the action", "winner": winner},
                )
            ]
        )

    return FunctionModel(model_fn)


def _always_first_pair_judge() -> FunctionModel:
    """A maximally position-biased judge: always picks whatever is shown first."""

    def model_fn(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        out = (info.output_tools or [])[0].name
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=out,
                    args={"reasoning": "first looks fine", "winner": "first"},
                )
            ]
        )

    return FunctionModel(model_fn)


def test_better_answer_wins_in_both_positions() -> None:
    judge: Agent[None, PairVerdict] = build_pairwise_judge(
        "anthropic:claude-sonnet-4-6"
    )
    with judge.override(model=_content_aware_pair_judge()):
        assert pairwise_winner(_GOOD_REASON, _BAD_REASON, judge=judge) == "a"


def test_swap_makes_b_win_when_b_is_better() -> None:
    judge: Agent[None, PairVerdict] = build_pairwise_judge(
        "anthropic:claude-sonnet-4-6"
    )
    with judge.override(model=_content_aware_pair_judge()):
        assert pairwise_winner(_BAD_REASON, _GOOD_REASON, judge=judge) == "b"


def test_position_bias_collapses_to_a_tie() -> None:
    # The judge picks "first" both times — it disagrees with itself across orders,
    # so the swap refuses to call it a win. That non-signal is the point.
    judge: Agent[None, PairVerdict] = build_pairwise_judge(
        "anthropic:claude-sonnet-4-6"
    )
    with judge.override(model=_always_first_pair_judge()):
        assert pairwise_winner(_GOOD_REASON, _BAD_REASON, judge=judge) == "tie"


def test_pairwise_costs_exactly_two_calls() -> None:
    calls: list[int] = []
    judge: Agent[None, PairVerdict] = build_pairwise_judge(
        "anthropic:claude-sonnet-4-6"
    )
    with judge.override(model=_content_aware_pair_judge(calls=calls)):
        pairwise_winner(_GOOD_REASON, _BAD_REASON, judge=judge)
    assert len(calls) == 2  # forward + reverse, always — the price of no position bias


# --- calibration: chance-corrected and ordinal-aware -----------------------------


def test_perfect_agreement_is_kappa_one() -> None:
    grades = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]
    assert calibrate(grades, grades) == pytest.approx(1.0)


def test_misaligned_graded_sets_raise() -> None:
    with pytest.raises(ValueError, match="aligned 1:1"):
        calibrate([1, 2, 3], [1, 2])


def test_quadratic_weighting_forgives_near_misses() -> None:
    human = [1, 2, 3, 4, 5, 5, 4, 3, 2, 1]
    near = [1, 2, 3, 4, 4, 5, 4, 3, 2, 1]  # one 5→4
    far = [1, 2, 3, 4, 1, 5, 4, 3, 2, 1]  # the same slot, 5→1
    kappa_near = calibrate(human, near)
    kappa_far = calibrate(human, far)
    assert kappa_near > kappa_far
    assert kappa_near == pytest.approx(0.973, abs=0.01)
    assert kappa_far == pytest.approx(0.60, abs=0.01)


def test_chance_correction_deflates_lucky_agreement() -> None:
    # A judge that always says "1" agrees with mostly-1 humans 80% of the time by
    # raw count — and earns a kappa of 0.0, because that agreement is all luck.
    mostly_one = [1, 1, 1, 1, 1, 1, 1, 1, 2, 3]
    always_one = [1] * 10
    assert calibrate(mostly_one, always_one) == pytest.approx(0.0, abs=1e-9)
