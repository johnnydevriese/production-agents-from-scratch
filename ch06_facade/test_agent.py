"""Agent-wiring test — offline via PydanticAI's FunctionModel. Zero spend.

We don't call a provider; we script the model with a `FunctionModel` that emits
one exact tool call, then asserts the agent routed it through the facade deps and
got a typed result back. The provider key is never read.
"""

from __future__ import annotations

from datetime import date

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .agent import ap_agent
from .facade import RailPaymentFacade
from .rail import FakeRail


def _drive_check_budget() -> FunctionModel:
    """A scripted model: first turn calls check_budget, second turn answers."""
    calls = {"n": 0}

    def model_fn(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        if calls["n"] == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="check_budget",
                        args={"department": "Engineering", "amount": "2988.09"},
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="Within budget, $1,011.91 left.")])

    return FunctionModel(model_fn)


def test_agent_routes_a_tool_call_through_the_facade() -> None:
    facade = RailPaymentFacade(rail=FakeRail(value_date=date(2026, 7, 12)))

    with ap_agent.override(model=_drive_check_budget()):
        result = ap_agent.run_sync(
            "Is INV-1043 within the Engineering budget?", deps=facade
        )

    assert "within budget" in result.output.lower()
    # The tool's typed BudgetCheck result is in the run's messages.
    assert any(
        "budget_remaining" in str(part)
        for message in result.all_messages()
        for part in getattr(message, "parts", [])
    )


def test_agent_registers_the_seven_tools() -> None:
    # The bounded menu, as the framework sees it.
    registered = set(ap_agent._function_toolset.tools)  # pyright: ignore[reportPrivateUsage]
    assert registered == {
        "lookup_invoice",
        "get_vendor",
        "match_to_po",
        "check_budget",
        "request_approval",
        "schedule_payment",
        "post_journal_entry",
    }
