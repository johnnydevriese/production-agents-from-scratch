"""The backend seam: group a turn into a thread, then score it.

The only backend-specific surface is `TraceSink` — the one method we call on the
tracing backend. A real run passes Opik's `opik_context` (which exposes exactly
this `update_current_trace`); the tests pass a recorder and assert the thread key
and the scores offline, at zero cost. That keeps the rest of the chapter
backend-neutral, which is the whole reason Chapter 17 emitted plain OTel.

In production this is the body of an `@opik.track`-decorated turn:

    @opik.track(name="ap_turn", project_name="ap-autopilot")
    async def run_turn(*, invoice_id, session_id, deps) -> str:
        result = await autopilot.run(invoice_id, deps=deps)   # the Ch 17 span tree
        record_turn(
            sink=opik.opik_context,
            invoice_id=invoice_id,
            new_turn_messages=result.new_messages(),
            match=deps.last_match,
        )
        return result.output

`record_turn` itself is sync and pure-ish: it derives facts and hands them to the
sink, so it tests without a server.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from pydantic_ai.messages import ModelMessage

from autopilot import InvoiceId, MatchResult

from .feedback import FeedbackPayload, derive_feedback, tools_fired


class TraceSink(Protocol):
    """The one method we need from the tracing backend (Opik's `opik_context`)."""

    def update_current_trace(
        self,
        *,
        thread_id: str | None = ...,
        input: Mapping[str, object] | None = ...,
        tags: list[str] | None = ...,
        feedback_scores: list[dict[str, object]] | None = ...,
    ) -> None: ...


def thread_key(invoice_id: InvoiceId | str) -> str:
    """The grouping key: one invoice's whole journey from RECEIVED to PAID.

    The autopilot has no chat session, but it has a *case*. Threading on the
    invoice stitches the four traces hours apart — match, escalate, approve, pay —
    into one timeline you can walk from symptom back to cause.
    """
    return f"invoice:{invoice_id}"


def record_turn(
    *,
    sink: TraceSink,
    invoice_id: InvoiceId | str,
    new_turn_messages: Sequence[ModelMessage],
    match: MatchResult | None,
) -> FeedbackPayload:
    """Thread this turn under its invoice, then write the path-derived scores."""
    sink.update_current_trace(
        thread_id=thread_key(invoice_id),
        input={"invoice_id": invoice_id},
    )
    payload = derive_feedback(fired=tools_fired(new_turn_messages), match=match)
    sink.update_current_trace(tags=payload.tags, feedback_scores=payload.score_dicts())
    return payload
