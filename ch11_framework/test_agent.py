"""ch11 — the framework checkpoint, offline and zero-spend.

Three things the framework bought us, each pinned by a test: the JSON schema is
DERIVED from the signature (no hand-written `TOOL_SCHEMAS`/`DISPATCH` to drift),
the Chapter 10 money-movement gate is wired in as a PydanticAI validator (a
`ModelRetry` that degrades to a human — the model can't bypass it), and PydanticAI
emits the Chapter 4 `gen_ai.*` spans near-free.
"""

from __future__ import annotations

from datetime import date

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from autopilot.fixtures import VENDORS
from autopilot.models import VendorId
from ch06_facade.facade import RailPaymentFacade
from ch06_facade.rail import FakeRail
from ch10_guardrails.guardrails import GuardrailTripped

from .agent import Deps, autopilot

FROZEN_TOOLS = {
    "lookup_invoice",
    "get_vendor",
    "match_to_po",
    "check_budget",
    "request_approval",
    "schedule_payment",
    "post_journal_entry",
}


def _deps(*, confirmed: bool) -> tuple[Deps, FakeRail]:
    rail = FakeRail(value_date=date(2026, 6, 30))
    return Deps(tools=RailPaymentFacade(rail=rail), confirmed=confirmed), rail


def _pay_then_escalate() -> FunctionModel:
    """Always tries schedule_payment first, then degrades to request_approval if the
    gate sends back a ModelRetry. Identical model behavior in both confirmed states —
    the CODE decides the outcome, not the prompt."""

    def model_fn(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        parts = [p for m in messages for p in getattr(m, "parts", [])]
        returned = {p.tool_name for p in parts if isinstance(p, ToolReturnPart)}
        retried = any(isinstance(p, RetryPromptPart) for p in parts)
        if "schedule_payment" in returned:
            return ModelResponse(parts=[TextPart(content="Payment scheduled.")])
        if "request_approval" in returned:
            return ModelResponse(parts=[TextPart(content="Escalated for approval.")])
        if retried:  # the gate tripped — degrade to a human
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="request_approval",
                        args={"invoice_id": "INV-1043", "reason": "money gate tripped"},
                    )
                ]
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="schedule_payment",
                    args={"invoice_id": "INV-1043", "idempotency_key": "k-1"},
                )
            ]
        )

    return FunctionModel(model_fn)


def _tools_called(result: object) -> list[str]:
    messages = result.all_messages()  # pyright: ignore[reportAttributeAccessIssue]
    return [
        p.tool_name
        for m in messages
        for p in getattr(m, "parts", [])
        if isinstance(p, ToolCallPart)
    ]


def test_schema_is_derived_for_the_seven_tools() -> None:
    # No hand-written TOOL_SCHEMAS / DISPATCH — the decorator IS the registration,
    # and the schema comes from the signature, so there is no second copy to drift.
    assert set(autopilot._function_toolset.tools) == FROZEN_TOOLS  # pyright: ignore[reportPrivateUsage]
    check_budget = autopilot._function_toolset.tools["check_budget"]  # pyright: ignore[reportPrivateUsage]
    props = check_budget.tool_def.parameters_json_schema["properties"]
    assert {"department", "amount"} <= set(props)


def test_unconfirmed_money_move_degrades_to_a_human() -> None:
    deps, rail = _deps(confirmed=False)
    with autopilot.override(model=_pay_then_escalate()):
        result = autopilot.run_sync("Pay INV-1043.", deps=deps)
    assert "request_approval" in _tools_called(result)  # the gate routed it to a human
    assert rail.calls == []  # the load-bearing assertion: no money moved


def test_confirmation_releases_the_payment() -> None:
    deps, rail = _deps(confirmed=True)
    with autopilot.override(model=_pay_then_escalate()):
        autopilot.run_sync("Pay INV-1043.", deps=deps)
    assert len(rail.calls) == 1  # a human-set flag the model can't forge


def test_output_validator_blocks_a_leaked_vendor_secret() -> None:
    leaked = VENDORS[VendorId("V-ACME")].bank_account

    def _leak(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(content=f"Sent to account {leaked}.")])

    deps, _rail = _deps(confirmed=True)
    with (
        autopilot.override(model=FunctionModel(_leak)),
        pytest.raises(GuardrailTripped),
    ):
        autopilot.run_sync("Pay INV-1043.", deps=deps)


def test_instrumentation_emits_gen_ai_spans() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    deps, _rail = _deps(confirmed=True)
    with autopilot.override(model=_pay_then_escalate()):
        autopilot.run_sync("Pay INV-1043.", deps=deps)

    keys = {k for s in exporter.get_finished_spans() for k in (s.attributes or {})}
    assert any(k.startswith("gen_ai.") for k in keys)
