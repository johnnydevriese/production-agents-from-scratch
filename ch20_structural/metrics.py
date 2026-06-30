"""Tool precision / recall / F1 — scoring the path as a set-prediction problem.

A single case gets a pass/fail from an evaluator. A *suite* needs a number you can
track across changes. Treat "which tools the agent called" as a prediction against
"which tools it should have called" and borrow the metric every classifier uses.

Pure code over two lists of tool names — no model, no span tree, no spend. The
transition counts (ordered adjacent pairs) make a *reordering* show up as a
false-positive transition, which a plain tool-set comparison would miss.

The asymmetry the chapter hammers: a false-positive `schedule_payment` is a real
duplicate payment, so you guard *precision* hardest on the money-movement tool;
skipping `check_budget` is a false negative, so you guard *recall* on the controls.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field


class ToolCounts(BaseModel):
    """Per-case (or aggregated) confusion counts for tools and their transitions."""

    tool_tp: int = Field(ge=0)  # required tools the agent called
    tool_fp: int = Field(ge=0)  # tools it called that it shouldn't have
    tool_fn: int = Field(ge=0)  # required tools it skipped
    transition_tp: int = Field(ge=0)
    transition_fp: int = Field(ge=0)
    transition_fn: int = Field(ge=0)
    tool_call_count: int = Field(ge=0)  # total calls, including duplicates

    @property
    def step_efficiency(self) -> float:
        """Of all calls the agent made, the fraction that were required. A
        double-pay drags this down; so does any spurious call."""
        if self.tool_call_count == 0:
            return 1.0
        return self.tool_tp / self.tool_call_count


def _transitions(tools: Sequence[str]) -> set[tuple[str, str]]:
    return set(zip(tools, tools[1:], strict=False))


def per_case_counts(*, expected: Sequence[str], actual: Sequence[str]) -> ToolCounts:
    """Sort the actual vs expected tool calls into tp / fp / fn, for both the tool
    *set* and the ordered *transitions* between consecutive tools."""
    expected_set, actual_set = set(expected), set(actual)
    expected_pairs, actual_pairs = _transitions(expected), _transitions(actual)
    return ToolCounts(
        tool_tp=len(actual_set & expected_set),
        tool_fp=len(actual_set - expected_set),
        tool_fn=len(expected_set - actual_set),
        transition_tp=len(actual_pairs & expected_pairs),
        transition_fp=len(actual_pairs - expected_pairs),
        transition_fn=len(expected_pairs - actual_pairs),
        tool_call_count=len(actual),
    )


def aggregate(counts: Sequence[ToolCounts]) -> ToolCounts:
    """Sum per-case counts into one report-wide confusion count."""
    if not counts:
        raise ValueError("cannot aggregate an empty sequence of counts")
    return ToolCounts(
        tool_tp=sum(c.tool_tp for c in counts),
        tool_fp=sum(c.tool_fp for c in counts),
        tool_fn=sum(c.tool_fn for c in counts),
        transition_tp=sum(c.transition_tp for c in counts),
        transition_fp=sum(c.transition_fp for c in counts),
        transition_fn=sum(c.transition_fn for c in counts),
        tool_call_count=sum(c.tool_call_count for c in counts),
    )


def precision(counts: ToolCounts) -> float:
    """Of the tools it called, how many belonged. Guard this hardest on
    `schedule_payment`: a false positive there is a duplicate payment."""
    denom = counts.tool_tp + counts.tool_fp
    if denom == 0:
        raise ValueError("precision undefined: no tools were called")
    return counts.tool_tp / denom


def recall(counts: ToolCounts) -> float:
    """Of the tools it should have called, how many it did. Guard this on controls
    like `check_budget`: a false negative is a skipped safety step."""
    denom = counts.tool_tp + counts.tool_fn
    if denom == 0:
        raise ValueError("recall undefined: no tools were required")
    return counts.tool_tp / denom


def f1(counts: ToolCounts) -> float:
    """Harmonic mean — forces precision AND recall to be good at once. An agent that
    calls nothing has perfect precision; one that calls everything has perfect
    recall; only F1 punishes both failure modes."""
    p, r = precision(counts), recall(counts)
    if p + r == 0:
        raise ValueError("F1 undefined: precision and recall both zero")
    return 2 * p * r / (p + r)
