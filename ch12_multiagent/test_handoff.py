"""ch12 — the handoff is a typed payload, and a discrepancy holds the money leg.

Reconciliation emits a `MatchResult` (a validated object, not prose); the
supervisor passes it to AP, which settles the invoice the object names. A clean
match pays; a `MatchResult` carrying a discrepancy holds the payment for a human —
the rail never disburses.
"""

from __future__ import annotations

import asyncio
from datetime import date

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from autopilot import MatchResult
from ch06_facade.facade import RailPaymentFacade
from ch06_facade.rail import FakeRail

from .handoff import ap_agent, reconcile_then_settle, reconciliation_agent


def _emit_match(*, matched: bool, discrepancies: list[str]) -> FunctionModel:
    def model_fn(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        output_tool = (info.output_tools or [])[0].name
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=output_tool,
                    args={
                        "invoice_id": "INV-1043",
                        "matched": matched,
                        "purchase_order_id": "PO-7781",
                        "discrepancies": discrepancies,
                    },
                )
            ]
        )

    return FunctionModel(model_fn)


def _settle() -> FunctionModel:
    def model_fn(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        from pydantic_ai.messages import ToolReturnPart

        done = {
            p.tool_name
            for m in messages
            for p in getattr(m, "parts", [])
            if isinstance(p, ToolReturnPart)
        }
        if "settle" in done:
            return ModelResponse(parts=[TextPart(content="Settled.")])
        # No invoice id in the prompt — AP reads it from the typed handoff.
        return ModelResponse(
            parts=[ToolCallPart(tool_name="settle", args={"idempotency_key": "k-1043"})]
        )

    return FunctionModel(model_fn)


def test_the_reconciliation_payload_is_a_typed_matchresult() -> None:
    with reconciliation_agent.override(
        model=_emit_match(matched=True, discrepancies=[])
    ):
        output = reconciliation_agent.run_sync("Reconcile INV-1043").output
    assert isinstance(output, MatchResult)  # a validated object, not a paragraph
    assert output.matched


def test_a_clean_match_hands_off_and_pays() -> None:
    rail = FakeRail(value_date=date(2026, 6, 30))
    facade = RailPaymentFacade(rail=rail)
    with (
        reconciliation_agent.override(
            model=_emit_match(matched=True, discrepancies=[])
        ),
        ap_agent.override(model=_settle()),
    ):
        result = asyncio.run(reconcile_then_settle("INV-1043", facade=facade))
    assert result == "Settled."
    assert len(rail.calls) == 1
    assert rail.calls[0].amount_cents == 298809  # AP paid the invoice recon named


def test_a_discrepancy_holds_the_payment() -> None:
    rail = FakeRail(value_date=date(2026, 6, 30))
    facade = RailPaymentFacade(rail=rail)
    with (
        reconciliation_agent.override(
            model=_emit_match(matched=True, discrepancies=["amount mismatch"])
        ),
        ap_agent.override(model=_settle()),
    ):
        result = asyncio.run(reconcile_then_settle("INV-1043", facade=facade))
    assert result is None  # held for a human
    assert rail.calls == []  # the money leg never ran
