"""Offline tests for Chapter 17. No network, no API key, zero spend.

`messages.create` is replaced with a function that replays scripted `Message`s,
and spans are captured by an in-memory exporter — so the whole span tree
(root → chat → tool, the gen_ai.* conventions, the risk tier, the token climb,
the discrepancy event) is asserted without touching a provider.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import anthropic
import pytest
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pydantic import BaseModel

from autopilot.models import InvoiceId, MatchResult

from .traced_loop import configure_tracer, run_autopilot


def _msg(
    *,
    stop_reason: str,
    blocks: list[TextBlock | ToolUseBlock],
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> Message:
    return Message(
        id="msg_test",
        content=list(blocks),
        model="claude-sonnet-4-6",
        role="assistant",
        stop_reason=stop_reason,  # pyright: ignore[reportArgumentType]
        stop_sequence=None,
        type="message",
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def _text(text: str) -> TextBlock:
    return TextBlock(text=text, type="text", citations=None)


def _tool_use(name: str, args: dict[str, Any], *, block_id: str) -> ToolUseBlock:
    return ToolUseBlock(id=block_id, name=name, input=args, type="tool_use")


def _scripted_client(responses: list[Message]) -> anthropic.Anthropic:
    client = anthropic.Anthropic(api_key="test-key-unused")
    pending = iter(responses)

    def fake_create(**_kwargs: Any) -> Message:
        return next(pending)

    object.__setattr__(client.messages, "create", fake_create)
    return client


def _by_name(spans: tuple[ReadableSpan, ...]) -> dict[str, ReadableSpan]:
    return {s.name: s for s in spans}


def _attrs(span: ReadableSpan) -> dict[str, Any]:
    assert span.attributes is not None
    return dict(span.attributes)


# --- the tree: every span hangs off the one run ----------------------------------


def test_spans_nest_into_one_tree_under_the_run() -> None:
    exporter = InMemorySpanExporter()
    tracer = configure_tracer(exporter)
    client = _scripted_client(
        [
            _msg(
                stop_reason="tool_use",
                blocks=[
                    _tool_use("match_to_po", {"invoice_id": "INV-1043"}, block_id="t1")
                ],
            ),
            _msg(stop_reason="end_turn", blocks=[_text("Matched to PO-7781.")]),
        ]
    )

    run_autopilot("INV-1043", client=client, tracer=tracer)

    by_name = _by_name(exporter.get_finished_spans())
    assert {"autopilot.run", "chat", "match_to_po"} <= set(by_name)
    root_ctx = by_name["autopilot.run"].context
    assert root_ctx is not None
    # Both the model-call span and the tool span are children of the run span:
    # the nesting `with` blocks built the tree, no parent IDs wired by hand.
    for child in ("chat", "match_to_po"):
        parent = by_name[child].parent
        assert parent is not None
        assert parent.span_id == root_ctx.span_id


# --- the tool span: named after the tool, tagged with the frozen risk tier --------


def test_tool_span_is_named_after_the_tool_and_carries_the_risk_tier() -> None:
    exporter = InMemorySpanExporter()
    tracer = configure_tracer(exporter)
    client = _scripted_client(
        [
            _msg(
                stop_reason="tool_use",
                blocks=[
                    _tool_use("match_to_po", {"invoice_id": "INV-1043"}, block_id="t1")
                ],
            ),
            _msg(stop_reason="end_turn", blocks=[_text("done")]),
        ]
    )

    run_autopilot("INV-1043", client=client, tracer=tracer)

    tool_span = _by_name(exporter.get_finished_spans())["match_to_po"]
    attrs = _attrs(tool_span)
    assert attrs["gen_ai.tool.name"] == "match_to_po"
    assert attrs["tool.risk_tier"] == "read_only"  # Ch 3 taxonomy, frozen canon
    assert attrs["tool.ok"] is True
    assert attrs["tool.matched"] is True  # INV-1043 has a PO


def test_request_approval_span_carries_its_external_comms_tier() -> None:
    exporter = InMemorySpanExporter()
    tracer = configure_tracer(exporter)
    client = _scripted_client(
        [
            _msg(
                stop_reason="tool_use",
                blocks=[
                    _tool_use(
                        "request_approval",
                        {"invoice_id": "INV-1043", "reason": "PO mismatch"},
                        block_id="t1",
                    )
                ],
            ),
            _msg(stop_reason="end_turn", blocks=[_text("Escalated.")]),
        ]
    )

    run_autopilot("INV-1043", client=client, tracer=tracer)

    attrs = _attrs(_by_name(exporter.get_finished_spans())["request_approval"])
    assert attrs["tool.risk_tier"] == "external_comms"


# --- the chat span: the gen_ai.* semantic conventions ----------------------------


def test_chat_span_carries_the_gen_ai_conventions() -> None:
    exporter = InMemorySpanExporter()
    tracer = configure_tracer(exporter)
    client = _scripted_client(
        [_msg(stop_reason="end_turn", blocks=[_text("All set.")])]
    )

    run_autopilot("INV-1043", client=client, tracer=tracer)

    attrs = _attrs(_by_name(exporter.get_finished_spans())["chat"])
    assert attrs["gen_ai.system"] == "anthropic"
    assert attrs["gen_ai.request.model"] == "claude-sonnet-4-6"
    assert attrs["gen_ai.operation.name"] == "chat"
    assert attrs["gen_ai.usage.input_tokens"] == 10
    assert attrs["gen_ai.usage.output_tokens"] == 5
    assert "end_turn" in attrs["gen_ai.response.finish_reasons"]


def test_input_tokens_climb_across_model_calls() -> None:
    # Chapter 1's warning, now measured per call: the window grows as results
    # are appended, so call #2's prompt is larger than call #1's.
    exporter = InMemorySpanExporter()
    tracer = configure_tracer(exporter)
    client = _scripted_client(
        [
            _msg(
                stop_reason="tool_use",
                blocks=[
                    _tool_use(
                        "lookup_invoice", {"invoice_id": "INV-1043"}, block_id="t1"
                    )
                ],
                input_tokens=1840,
            ),
            _msg(stop_reason="end_turn", blocks=[_text("done")], input_tokens=2110),
        ]
    )

    run_autopilot("INV-1043", client=client, tracer=tracer)

    chat_spans = [s for s in exporter.get_finished_spans() if s.name == "chat"]
    by_start = sorted(chat_spans, key=lambda s: s.start_time or 0)
    tokens = [_attrs(s)["gen_ai.usage.input_tokens"] for s in by_start]
    assert tokens == [1840, 2110]


# --- the root span: business attributes and outcome ------------------------------


def test_root_records_the_invoice_and_an_escalation_outcome() -> None:
    exporter = InMemorySpanExporter()
    tracer = configure_tracer(exporter)
    client = _scripted_client(
        [
            _msg(
                stop_reason="tool_use",
                blocks=[
                    _tool_use(
                        "request_approval",
                        {"invoice_id": "INV-1043", "reason": "PO mismatch"},
                        block_id="t1",
                    )
                ],
            ),
            _msg(stop_reason="end_turn", blocks=[_text("Escalated.")]),
        ]
    )

    run_autopilot("INV-1043", client=client, tracer=tracer)

    attrs = _attrs(_by_name(exporter.get_finished_spans())["autopilot.run"])
    assert attrs["invoice.id"] == "INV-1043"
    assert attrs["autopilot.outcome"] == "needs_approval"


def test_clean_path_completes_without_escalation() -> None:
    exporter = InMemorySpanExporter()
    tracer = configure_tracer(exporter)
    client = _scripted_client(
        [
            _msg(
                stop_reason="tool_use",
                blocks=[
                    _tool_use(
                        "lookup_invoice", {"invoice_id": "INV-1043"}, block_id="t1"
                    )
                ],
            ),
            _msg(stop_reason="end_turn", blocks=[_text("Within budget.")]),
        ]
    )

    run_autopilot("INV-1043", client=client, tracer=tracer)

    attrs = _attrs(_by_name(exporter.get_finished_spans())["autopilot.run"])
    assert attrs["autopilot.outcome"] == "completed"


# --- attributes describe the span; events mark moments inside it ------------------


def test_a_discrepancy_is_an_event_not_an_attribute() -> None:
    exporter = InMemorySpanExporter()
    tracer = configure_tracer(exporter)
    client = _scripted_client(
        [
            _msg(
                stop_reason="tool_use",
                blocks=[
                    _tool_use("match_to_po", {"invoice_id": "INV-1051"}, block_id="t1")
                ],
            ),
            _msg(stop_reason="end_turn", blocks=[_text("Mismatch.")]),
        ]
    )

    def _mismatch(**_kwargs: Any) -> MatchResult:
        return MatchResult(
            invoice_id=InvoiceId("INV-1051"),
            matched=False,
            discrepancies=["qty 10 vs 8; price 12.40 vs 12.10"],
        )

    dispatch: dict[str, Callable[..., BaseModel]] = {"match_to_po": _mismatch}
    run_autopilot("INV-1051", client=client, tracer=tracer, dispatch=dispatch)

    tool_span = _by_name(exporter.get_finished_spans())["match_to_po"]
    assert _attrs(tool_span)["tool.matched"] is False
    events = [e.name for e in tool_span.events]
    assert "discrepancy" in events  # a timestamped moment, not a span attribute


# --- a failing tool is visible from the tree -------------------------------------


def test_a_failed_tool_marks_its_span_not_ok() -> None:
    exporter = InMemorySpanExporter()
    tracer = configure_tracer(exporter)
    client = _scripted_client(
        [
            _msg(
                stop_reason="tool_use",
                blocks=[
                    _tool_use(
                        "lookup_invoice", {"invoice_id": "INV-9999"}, block_id="t1"
                    )
                ],
            ),
        ]
    )

    def _missing(**_kwargs: Any) -> BaseModel:
        raise LookupError("INV-9999")

    dispatch: dict[str, Callable[..., BaseModel]] = {"lookup_invoice": _missing}
    with pytest.raises(LookupError):
        run_autopilot("INV-9999", client=client, tracer=tracer, dispatch=dispatch)

    tool_span = _by_name(exporter.get_finished_spans())["lookup_invoice"]
    assert _attrs(tool_span)["tool.ok"] is False


# --- tracing is observation, not behavior ----------------------------------------


def test_the_answer_is_the_models_text_regardless_of_tracing() -> None:
    exporter = InMemorySpanExporter()
    tracer = configure_tracer(exporter)
    client = _scripted_client(
        [_msg(stop_reason="end_turn", blocks=[_text("INV-1043 is within budget.")])]
    )

    answer = run_autopilot("INV-1043", client=client, tracer=tracer)

    assert answer == "INV-1043 is within budget."  # instrumentation changed nothing
