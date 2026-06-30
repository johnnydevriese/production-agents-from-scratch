"""The pointwise judge for the autopilot's free-text `reason` field.

A structural check (Chapter 20) asks a question with a *true* answer — did
`schedule_payment` fire exactly once? This asks one with a *graded opinion* — is
this approval reason specific enough for a controller to act on? There is no
assertion to write, so a second model call applies a rubric and emits a verdict.

Two design choices in `Verdict` are load-bearing, not decoration:

* The verdict is **structured, not a bare number.** A judge that returns `4` is a
  black box; one that returns the quote it graded and *why* is auditable — you can
  read a wrong score and see how it went wrong.
* **Evidence comes first; the grade comes last.** The model generates
  left-to-right, so forcing it to quote the span and reason *before* it commits to
  a number conditions the number on real reasoning. Put the grade first and the
  reasoning is post-hoc rationalization. The field order steers the computation
  (Chapter 9).

The judge is *injected*, never constructed inside the scoring function — and it
should be a different model family than the agent under test, or self-enhancement
bias makes it flatter its own outputs (Chapter 22).
"""

from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName, Model

from autopilot import ApprovalRequest, MatchResult


class Grade(IntEnum):
    UNUSABLE = 1  # true but content-free ("requires manual review")
    VAGUE = 2  # gestures at an issue, no specifics
    ADEQUATE = 3  # names the issue, missing a number or next step
    GOOD = 4  # names the issue + the specifics an approver needs
    EXCELLENT = 5  # GOOD, plus the exact action required


class Verdict(BaseModel):
    evidence_quote: str = Field(
        description="The exact span of the reason you are grading. Quote it."
    )
    reasoning: str = Field(
        description="Why this evidence earns this grade, citing the rubric."
    )
    grade: Grade


JUDGE_SYSTEM = """You grade accounts-payable approval reasons for an AP
controller who must act on them. A good reason names the specific discrepancy
AND the number/next-step the approver needs. Penalize vagueness even when the
text is true. You are grading specificity-for-action, not grammar.

Rubric:
  1 UNUSABLE   — true but content-free.
  2 VAGUE      — gestures at an issue, no specifics.
  3 ADEQUATE   — names the issue, missing a number or next step.
  4 GOOD       — names the issue and the specifics needed to act.
  5 EXCELLENT  — GOOD, plus the exact action required.
Quote the exact span you grade before you grade it."""


def build_reason_judge(model: Model | KnownModelName) -> Agent[None, Verdict]:
    """Wire the rubric and verdict schema onto a model. Pick a *different* model
    family than the agent under test (self-enhancement bias, Chapter 22)."""
    return Agent(model, output_type=Verdict, system_prompt=JUDGE_SYSTEM)


def judge_reason(
    approval: ApprovalRequest,
    match: MatchResult,
    *,
    judge: Agent[None, Verdict],
) -> Verdict:
    """Score one approval reason. The judge is injected, never built here.

    The matcher's actual findings are fed in so the judge grades *faithfulness*
    ("does the reason report what the path found?") rather than mere plausibility
    ("does this sound good?"). Without ground truth a pointwise judge will happily
    hand a 4 to a confident, specific, entirely fabricated reason.
    """
    prompt = (
        f"Discrepancies the matcher actually found: {match.discrepancies}\n"
        f"Reason the agent wrote: {approval.reason!r}\n\n"
        "Grade the reason against the rubric."
    )
    return judge.run_sync(prompt).output
