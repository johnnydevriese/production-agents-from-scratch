"""The Chapter 2 loop, now emitting a span tree instead of print lines.

observe → think → act → observe — unchanged. We wrap each step in an
OpenTelemetry span: one root `autopilot.run` per invoice (the trace), a child
`chat` span per model call tagged with the `gen_ai.*` semantic conventions, and a
child span per tool call whose **name is the tool name** and that carries the
frozen risk tier (`TOOL_RISK`, the Chapter 3 taxonomy). The nesting `with` blocks
build the parent-child tree for free — `start_as_current_span` makes each new span
a child of whatever span is active.

Tracing is observation, not behavior: the loop, the tools, and the model call are
exactly Chapter 2's. The tracer is *injected* (the book's DI rule), so a real run
wires a `ConsoleSpanExporter` and the tests wire an `InMemorySpanExporter` and
assert the tree offline, at zero API cost.

Run it for real:
    export ANTHROPIC_API_KEY=sk-...
    uv run python -m ch17_tracing.traced_loop
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from typing import Any, cast

import anthropic
from anthropic.types import (
    Message,
    MessageParam,
    TextBlock,
    ToolParam,
    ToolResultBlockParam,
    ToolUseBlock,
)
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
)
from pydantic import BaseModel

from autopilot import TOOL_RISK

from .tool_schemas import TOOLS
from .tools_impl import DISPATCH

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = (
    "You are an accounts-payable autopilot. For the given invoice: match it to its "
    "purchase order, check the department budget, and decide. A clean match within "
    "budget may proceed; a mismatch or a missing PO must be escalated with "
    "request_approval and a reason. Never invent a fact — call the tool for it."
)


class AgentError(RuntimeError):
    """The loop could not finish — e.g. it hit the step cap without an answer."""


def configure_tracer(
    exporter: SpanExporter, *, name: str = "autopilot"
) -> trace.Tracer:
    """Build a tracer that ships finished spans to `exporter`.

    `SimpleSpanProcessor` exports each span as it ends — deterministic, which is
    what both the console demo and the offline tests want. Production swaps in a
    batching processor and an OTLP exporter (Chapter 18).
    """
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(name)


def run_autopilot(
    invoice_id: str,
    *,
    client: anthropic.Anthropic,
    tracer: trace.Tracer,
    dispatch: Mapping[str, Callable[..., BaseModel]] = DISPATCH,
    tools: list[ToolParam] = TOOLS,
    max_steps: int = 8,
) -> str:
    """Run the observe→think→act→observe loop, emitting one trace per invoice."""
    with tracer.start_as_current_span("autopilot.run") as root:
        root.set_attribute("invoice.id", invoice_id)  # business attribute
        messages: list[MessageParam] = [
            {"role": "user", "content": f"Process invoice {invoice_id}."}
        ]
        called: list[str] = []

        for _step in range(max_steps):
            response = _chat(client, tracer, messages=messages, tools=tools)

            if response.stop_reason != "tool_use":
                root.set_attribute("autopilot.outcome", _outcome(called))
                return _final_text(response)

            # Remember exactly what the model asked for, paired by tool_use_id.
            messages.append(
                cast("MessageParam", {"role": "assistant", "content": response.content})
            )
            results: list[ToolResultBlockParam] = []
            for block in response.content:
                if not isinstance(block, ToolUseBlock):
                    continue
                called.append(block.name)
                output = _dispatch_tool(tracer, block, dispatch=dispatch)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output.model_dump_json(),
                    }
                )
            messages.append({"role": "user", "content": results})  # reality back in

        root.set_attribute("autopilot.outcome", "exhausted")
        raise AgentError(f"did not finish within {max_steps} steps")


def _chat(
    client: anthropic.Anthropic,
    tracer: trace.Tracer,
    *,
    messages: list[MessageParam],
    tools: list[ToolParam],
) -> Message:
    """One model call, inside a CLIENT span tagged with the gen_ai.* conventions."""
    with tracer.start_as_current_span("chat", kind=trace.SpanKind.CLIENT) as span:
        span.set_attribute("gen_ai.system", "anthropic")
        span.set_attribute("gen_ai.request.model", MODEL)
        span.set_attribute("gen_ai.operation.name", "chat")
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )
        usage = response.usage
        span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
        span.set_attribute(
            "gen_ai.response.finish_reasons", [response.stop_reason or "unknown"]
        )
        return response


def _dispatch_tool(
    tracer: trace.Tracer,
    block: ToolUseBlock,
    *,
    dispatch: Mapping[str, Callable[..., BaseModel]],
) -> BaseModel:
    """Run one tool call inside an INTERNAL span. The tool name IS the span name."""
    args = cast("dict[str, Any]", block.input)
    with tracer.start_as_current_span(block.name, kind=trace.SpanKind.INTERNAL) as span:
        span.set_attribute("gen_ai.tool.name", block.name)
        span.set_attribute("tool.risk_tier", TOOL_RISK[block.name].value)  # Ch 3
        try:
            result = dispatch[block.name](**args)  # run it in OUR code
        except LookupError as exc:
            span.set_attribute("tool.ok", False)
            span.record_exception(exc)
            raise
        span.set_attribute("tool.ok", True)
        matched = getattr(result, "matched", None)
        if isinstance(matched, bool):
            span.set_attribute("tool.matched", matched)
        discrepancies = getattr(result, "discrepancies", None)
        if discrepancies:  # a moment inside the span, not a fact about it → event
            span.add_event("discrepancy", {"detail": "; ".join(discrepancies)})
        return result


def _final_text(response: Message) -> str:
    return "".join(b.text for b in response.content if isinstance(b, TextBlock))


def _outcome(called: list[str]) -> str:
    return "needs_approval" if "request_approval" in called else "completed"


def main() -> None:
    tracer = configure_tracer(ConsoleSpanExporter())
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    answer = run_autopilot("INV-1043", client=client, tracer=tracer)
    print("--- answer ---")
    print(answer)


if __name__ == "__main__":
    main()
