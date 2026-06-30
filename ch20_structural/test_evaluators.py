"""ch20 — structural evals over the REAL agent's span tree.

The rule the chapter is built on: test the agent, never a mock of the model. Each
test drives the actual ch11 autopilot — real system prompt, real tool schemas, real
loop — with a `FunctionModel` standing in for the network (offline, zero spend). The
model is *not* scripted into the assertions: the agent's loop dispatches the tool
calls through the real (faked-at-the-boundary) tools, emits spans, and the
evaluators read those spans. A mocked model that hand-fed the tool list would assert
that the *fixture* paid once — which tells you nothing about the agent.

The double-pay is the proof: a model that emits `schedule_payment` twice produces a
tree where `ToolCallCount("schedule_payment", 1)` fails with `got 2` — the exact
failure a perfect *answer* hid in the motivating story.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_evals.evaluators import EvaluationReason

from ch11_framework.agent import Deps, autopilot

from .evaluators import ToolCallCount, ToolCallSequence, ToolNotCalled, tool_called
from .harness import RecordingTools, capture_tree, context_for

# Smoke lane: every case is a live LLM round trip (offline here via FunctionModel),
# but no DB — fast enough to gate every PR. The full-stack lane lands with Ch 25/26.
pytestmark = [pytest.mark.span_eval, pytest.mark.eval_smoke]

_ENTRY = {
    "invoice_id": "INV-1043",
    "debit_account": "5000-Engineering",
    "credit_account": "2000-AP",
    "amount": "2988.09",
}


def _script(tool_calls: list[tuple[str, dict[str, Any]]]) -> FunctionModel:
    """A model that emits ONE tool call per turn, then a clean final answer. One per
    turn (not a batch) is both the realistic path — the agent observes each result
    before deciding the next step — and the only way to get a deterministic order:
    PydanticAI dispatches multiple tool calls in a *single* response concurrently, so
    a batch would scramble the sequence the order assertions depend on. The agent's
    loop — not this script — is what gets evaluated."""
    state = {"turn": 0}

    def fn(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        turn = state["turn"]
        state["turn"] += 1
        if turn < len(tool_calls):
            name, args = tool_calls[turn]
            return ModelResponse(parts=[ToolCallPart(tool_name=name, args=args)])
        return ModelResponse(parts=[TextPart(content="Done. INV-1043 handled.")])

    return FunctionModel(fn)


_HAPPY_PATH = [
    ("check_budget", {"department": "Engineering", "amount": "2988.09"}),
    ("request_approval", {"invoice_id": "INV-1043", "reason": "high value"}),
    ("schedule_payment", {"invoice_id": "INV-1043", "idempotency_key": "k-1043"}),
    ("post_journal_entry", {"entry": _ENTRY}),
]


def _run(tool_calls: list[tuple[str, dict[str, Any]]]) -> tuple[Any, RecordingTools]:
    tools = RecordingTools()
    deps = Deps(tools=tools, confirmed=True)
    with autopilot.override(model=_script(tool_calls)):
        tree = capture_tree(autopilot, "Process invoice INV-1043.", deps=deps)
    return context_for(tree), tools


def test_happy_path_calls_the_payment() -> None:
    ctx, _tools = _run(_HAPPY_PATH)
    assert tool_called("schedule_payment").evaluate(ctx) is True


def test_we_test_the_real_agent_not_a_mock() -> None:
    # The boundary fake recorded exactly the tools the real loop dispatched — proof
    # the agent (not the test) drove the path the evaluators are scoring.
    _ctx, tools = _run(_HAPPY_PATH)
    assert tools.calls == [
        "check_budget",
        "request_approval",
        "schedule_payment",
        "post_journal_entry",
    ]


def test_exact_count_catches_the_double_pay() -> None:
    ctx, _tools = _run(
        [
            ("check_budget", {"department": "Engineering", "amount": "2988.09"}),
            ("schedule_payment", {"invoice_id": "INV-1043", "idempotency_key": "k1"}),
            ("schedule_payment", {"invoice_id": "INV-1043", "idempotency_key": "k2"}),
        ]
    )
    verdict = ToolCallCount("schedule_payment", expected_count=1).evaluate(ctx)
    assert isinstance(verdict, EvaluationReason)  # failed
    assert verdict.reason is not None and "got 2" in verdict.reason
    # "at least once" would have passed the double-pay — the trap the chapter names.
    assert tool_called("schedule_payment").evaluate(ctx) is True


def test_question_only_moves_no_money() -> None:
    ctx, _tools = _run([("lookup_invoice", {"invoice_id": "INV-1043"})])
    assert ToolNotCalled("schedule_payment").evaluate(ctx) is True
    assert ToolNotCalled("post_journal_entry").evaluate(ctx) is True


def test_sequence_holds_on_the_happy_path() -> None:
    ctx, _tools = _run(_HAPPY_PATH)
    seq = ToolCallSequence(
        ["check_budget", "request_approval", "schedule_payment", "post_journal_entry"]
    )
    assert seq.evaluate(ctx) is True


def test_sequence_fails_when_the_gl_entry_precedes_payment() -> None:
    ctx, _tools = _run(
        [
            ("check_budget", {"department": "Engineering", "amount": "2988.09"}),
            ("post_journal_entry", {"entry": _ENTRY}),  # booked before paying
            ("schedule_payment", {"invoice_id": "INV-1043", "idempotency_key": "k1"}),
        ]
    )
    verdict = ToolCallSequence(["schedule_payment", "post_journal_entry"]).evaluate(ctx)
    assert isinstance(verdict, EvaluationReason)  # the out-of-order path fails
