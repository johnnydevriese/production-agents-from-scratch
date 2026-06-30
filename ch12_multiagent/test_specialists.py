"""ch12 — the structural fix, pinned without an LLM.

The chapter's load-bearing claim is *structural*: the reporting specialist cannot
pay because `schedule_payment` is not in its menu. That's a fact about the
registered toolset, so these tests assert on the toolset directly — no model, no
spend. The one test that does run a model proves the other half: even a model that
*tries* to pay on the reporting agent cannot, because there is no such tool to call.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from autopilot import Specialist
from autopilot.tools import TOOL_RISK, RiskTier
from ch06_facade.facade import RailPaymentFacade
from ch06_facade.rail import FakeRail

from .specialists import SPECIALISTS, Deps

MONEY_MOVEMENT = {"schedule_payment", "post_journal_entry"}


def _menu(specialist: Specialist) -> set[str]:
    return set(SPECIALISTS[specialist]._function_toolset.tools)  # pyright: ignore[reportPrivateUsage]


def test_only_ap_holds_a_money_movement_tool() -> None:
    for specialist in Specialist:
        has_money = _menu(specialist) & MONEY_MOVEMENT
        assert bool(has_money) == (specialist is Specialist.AP), specialist


def test_reporting_cannot_even_see_schedule_payment() -> None:
    menu = _menu(Specialist.REPORTING)
    assert "schedule_payment" not in menu
    assert "post_journal_entry" not in menu
    assert menu == {"lookup_invoice", "check_budget"}  # read-only, by construction


def test_every_menu_is_a_subset_of_the_frozen_tools() -> None:
    frozen = set(TOOL_RISK)
    for specialist in Specialist:
        assert _menu(specialist) <= frozen, specialist  # no specialist invented a tool


def test_no_read_only_specialist_can_take_a_dangerous_action() -> None:
    dangerous = {
        name for name, tier in TOOL_RISK.items() if tier is not RiskTier.READ_ONLY
    }
    for specialist in (Specialist.REPORTING, Specialist.RECONCILIATION):
        assert not (_menu(specialist) & dangerous), specialist


def _tries_to_pay() -> FunctionModel:
    """A misbehaving reporting model that keeps reaching for schedule_payment."""

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


def test_a_rogue_reporting_model_still_cannot_pay() -> None:
    rail = FakeRail(value_date=date(2026, 6, 30))
    deps = Deps(tools=RailPaymentFacade(rail=rail))
    reporting = SPECIALISTS[Specialist.REPORTING]
    with (
        reporting.override(model=_tries_to_pay()),
        pytest.raises(UnexpectedModelBehavior),  # the tool does not exist to call
    ):
        reporting.run_sync("Pay Acme right now.", deps=deps)
    assert rail.calls == []  # the load-bearing assertion: no money moved


def test_a_well_behaved_reporting_model_reads_a_budget() -> None:
    def model_fn(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        from pydantic_ai.messages import ToolReturnPart

        done = {
            p.tool_name
            for m in messages
            for p in getattr(m, "parts", [])
            if isinstance(p, ToolReturnPart)
        }
        if "check_budget" in done:
            return ModelResponse(
                parts=[TextPart(content="Engineering is over budget.")]
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="check_budget",
                    args={"department": "Engineering", "amount": "2988.09"},
                )
            ]
        )

    rail = FakeRail(value_date=date(2026, 6, 30))
    deps = Deps(tools=RailPaymentFacade(rail=rail))
    reporting = SPECIALISTS[Specialist.REPORTING]
    with reporting.override(model=FunctionModel(model_fn)):
        result = reporting.run_sync("How's the Engineering budget?", deps=deps)
    assert "budget" in result.output.lower()
    assert rail.calls == []  # reporting reads; it never moves money
