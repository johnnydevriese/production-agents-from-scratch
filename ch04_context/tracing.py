"""From print() to the first spans.

`print()` was right for one turn and collapses at eight: the output interleaves
and you can't tell which `match_to_po` belongs to which turn. The fix is
**tracing** — a *span* is a timed, structured record of one unit of work; a
*trace* is the tree of spans for one request. Wrapping each tool call in a span
tagged with its frozen risk tier turns "did the payment use a real PO?" into a
question you answer by reading the tree, not the reply.

We use OpenTelemetry with the `gen_ai.*` semantic conventions. The tracer is
*injected* (the book's DI rule): a real run wires a `ConsoleSpanExporter` (Opik
in Part VI); tests wire an `InMemorySpanExporter` and assert the tree offline.
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from functools import partial

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from pydantic import BaseModel

from autopilot.tools import TOOL_RISK


def configure_tracer(
    exporter: SpanExporter, *, name: str = "autopilot"
) -> trace.Tracer:
    """Build a tracer that ships finished spans to `exporter`.

    `SimpleSpanProcessor` exports each span as it ends — deterministic, which is
    what tests want. Production swaps in a batching processor (Chapter 17).
    """
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer(name)


@contextmanager
def agent_turn(tracer: trace.Tracer, *, turn: int) -> Generator[trace.Span]:
    """Open the parent span for one turn; tool spans nest under it as children."""
    with tracer.start_as_current_span("agent.turn") as span:
        span.set_attribute("agent.turn", turn)
        yield span


def run_tool_span(
    tracer: trace.Tracer,
    name: str,
    fn: Callable[..., BaseModel],
    /,
    *args: object,
    **kwargs: object,
) -> BaseModel:
    """Run one tool call inside a span tagged with its frozen risk tier."""
    with tracer.start_as_current_span(f"tool.{name}") as span:
        span.set_attribute("tool.name", name)
        span.set_attribute("tool.risk", TOOL_RISK[name].value)  # Ch 3 taxonomy
        result = fn(*args, **kwargs)
        matched = getattr(result, "matched", None)
        if matched is not None:
            span.set_attribute("tool.matched", matched)
        return result


def traced_dispatch(
    dispatch: Mapping[str, Callable[..., BaseModel]], *, tracer: trace.Tracer
) -> dict[str, Callable[..., BaseModel]]:
    """Wrap every tool in `dispatch` so calling it emits a risk-tagged span.

    Drops straight into `run_turn(..., dispatch=traced_dispatch(DISPATCH, tracer=t))`.
    """
    return {
        name: partial(run_tool_span, tracer, name, func)
        for name, func in dispatch.items()
    }
