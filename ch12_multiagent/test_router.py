"""ch12 — the router classifies and dispatches, and the report path can't pay.

The router's only output is a `Specialist`, so dispatch is total (every label maps
to an agent) and `KeyError`-proof. The end-to-end test runs the opening bug — an
"Acme report" request — through `handle` and proves it lands in the reporting
agent, which has no money-movement tool: even a rogue specialist there cannot pay.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from autopilot import Specialist
from ch06_facade.facade import RailPaymentFacade
from ch06_facade.rail import FakeRail

from .router import handle, router_agent
from .specialists import SPECIALISTS, Deps


def _route_to(specialist: Specialist) -> FunctionModel:
    def model_fn(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        output_tool = (info.output_tools or [])[0].name
        return ModelResponse(
            parts=[
                ToolCallPart(tool_name=output_tool, args={"response": specialist.value})
            ]
        )

    return FunctionModel(model_fn)


def _tries_to_pay() -> FunctionModel:
    def model_fn(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="schedule_payment",
                    args={"invoice_id": "INV-1043", "idempotency_key": "k"},
                )
            ]
        )

    return FunctionModel(model_fn)


def test_dispatch_is_total_over_the_label_space() -> None:
    # output_type=Specialist + this dict being keyed by every member = KeyError-proof.
    assert set(SPECIALISTS) == set(Specialist)


def test_router_classifies_a_report_as_reporting() -> None:
    with router_agent.override(model=_route_to(Specialist.REPORTING)):
        decision = router_agent.run_sync("Give me the reconciliation report for Acme.")
    assert decision.output is Specialist.REPORTING


def test_the_acme_report_request_cannot_move_money_end_to_end() -> None:
    rail = FakeRail(value_date=date(2026, 6, 30))
    deps = Deps(tools=RailPaymentFacade(rail=rail))
    reporting = SPECIALISTS[Specialist.REPORTING]
    with (
        router_agent.override(model=_route_to(Specialist.REPORTING)),
        reporting.override(model=_tries_to_pay()),
        pytest.raises(UnexpectedModelBehavior),
    ):
        asyncio.run(handle("Give me the reconciliation report for Acme.", deps=deps))
    assert rail.calls == []  # routed to reporting → no schedule_payment tool to call
