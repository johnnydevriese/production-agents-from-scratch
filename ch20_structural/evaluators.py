"""Structural evaluators — assertions over the agent's span tree.

The span tree (Chapter 17) *is* the path the agent took, recorded. A structural
eval is a deterministic assertion over that tree: "was `schedule_payment` called?"
is a query; "exactly once?" is a count; "before `post_journal_entry`?" is a
subsequence check. No LLM judge, no fuzzy matching — a tool either appears in the
tree or it does not.

These are real `pydantic_evals` evaluators. They read `ctx.span_tree`, which
`harness.capture_tree` populates from a real instrumented agent run. The tool spans
are the PydanticAI `gen_ai.*` convention: each tool call is a span named
`execute_tool <name>` carrying `gen_ai.tool.name`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic_evals.evaluators import (
    EvaluationReason,
    Evaluator,
    EvaluatorContext,
    HasMatchingSpan,
)

# A tool-execution span carries this attribute (PydanticAI's gen_ai convention).
_TOOL_NAME_ATTR = "gen_ai.tool.name"


def _failure(reason: str) -> EvaluationReason:
    return EvaluationReason(value=False, reason=reason)


def tool_called(tool_name: str) -> HasMatchingSpan:
    """A tool was called at least once."""
    return HasMatchingSpan(
        query={"has_attributes": {_TOOL_NAME_ATTR: tool_name}},
        evaluation_name=f"tool_called:{tool_name}",
    )


@dataclass
class ToolNotCalled(Evaluator[Any, Any]):
    """A tool was NEVER called — the negative is just as load-bearing. A read
    ("is INV-1043 within budget?") must assert this on every money-movement tool."""

    tool_name: str

    def evaluate(self, ctx: EvaluatorContext[Any, Any]) -> bool | EvaluationReason:
        # `ctx.span_tree` raises if no tree was captured — an infra error, not a soft
        # failure, so we let it propagate rather than guard for `None`.
        matches = ctx.span_tree.find(
            {"has_attributes": {_TOOL_NAME_ATTR: self.tool_name}}
        )
        if matches:
            return _failure(
                f"expected no calls to {self.tool_name}, got {len(matches)}"
            )
        return True


@dataclass
class ToolCallCount(Evaluator[Any, Any]):
    """Assert a tool was called EXACTLY ``expected_count`` times. This is the
    idempotency check: "at least once" passes the double-pay; only an exact count
    catches it."""

    tool_name: str
    expected_count: int

    def evaluate(self, ctx: EvaluatorContext[Any, Any]) -> bool | EvaluationReason:
        actual = len(
            ctx.span_tree.find({"has_attributes": {_TOOL_NAME_ATTR: self.tool_name}})
        )
        if actual == self.expected_count:
            return True
        return _failure(
            f"expected {self.expected_count} calls to {self.tool_name}, got {actual}"
        )


@dataclass
class ToolCallSequence(Evaluator[Any, Any]):
    """Assert tools were called in this relative order (gaps allowed): budget before
    approval, approval before payment, payment before the GL entry."""

    sequence: list[str]

    def evaluate(self, ctx: EvaluatorContext[Any, Any]) -> bool | EvaluationReason:
        tool_spans = ctx.span_tree.find({"has_attribute_keys": [_TOOL_NAME_ATTR]})
        called = [
            str(n.attributes[_TOOL_NAME_ATTR])
            for n in sorted(tool_spans, key=lambda n: n.start_timestamp)
        ]
        it = iter(called)
        if all(tool in it for tool in self.sequence):  # iterator-advance subsequence
            return True
        return _failure(f"expected tool sequence {self.sequence}, observed {called}")
