"""Automated feedback scores — the WHERE clause, written at trace time.

A feedback score is a named, typed fact about a run, promoted from buried-in-the-
span-tree to top-level-and-indexed. The high-leverage ones are written by *your
own code* on every turn, with no human in the loop, so that "paid without a clean
PO match" becomes `WHERE paid = 1 AND po_matched = 0` instead of a 28-hour scroll.

The load-bearing discipline: the scores are derived from the **path, not the
answer**. `paid` is true because `schedule_payment` *fired* — observed in the
PydanticAI message parts — never because the model *said* it paid. Derivation is
a pure function (tested here); writing it to the backend is a thin injected sink
(see `tracing.py`).
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field
from pydantic_ai.messages import ModelMessage, ToolCallPart

from autopilot import MatchResult


def tools_fired(messages: Sequence[ModelMessage]) -> list[str]:
    """Tool names that fired this turn, in order, from the message parts."""
    return [
        part.tool_name
        for msg in messages
        for part in msg.parts
        if isinstance(part, ToolCallPart)
    ]


class FeedbackScore(BaseModel):
    """One indexed, typed fact about a run — the unit a filter queries on."""

    name: str
    value: float


class FeedbackPayload(BaseModel):
    """What gets written onto the trace: free-text tags + indexed scores."""

    tags: list[str] = Field(default_factory=list)
    scores: list[FeedbackScore] = Field(default_factory=list)

    def score_dicts(self) -> list[dict[str, object]]:
        """The `feedback_scores=[...]` shape the backend SDK expects."""
        return [{"name": s.name, "value": s.value} for s in self.scores]


def derive_feedback(
    *, fired: Sequence[str], match: MatchResult | None
) -> FeedbackPayload:
    """Turn this turn's path into the indexed facts the incident query needs.

    Every value is a fact about *which tools fired*, never about the model's prose:
    `paid` checks that `schedule_payment` is in `fired`, `po_matched` reads the
    typed `MatchResult` the matcher returned — not a sentence the model wrote.
    """
    return FeedbackPayload(
        tags=["ap"],
        scores=[
            FeedbackScore(name="tool_called", value=float(bool(fired))),
            FeedbackScore(name="paid", value=float("schedule_payment" in fired)),
            FeedbackScore(
                name="po_matched", value=float(match is not None and match.matched)
            ),
        ],
    )
