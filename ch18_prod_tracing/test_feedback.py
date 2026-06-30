"""Offline tests for Chapter 18's feedback + threading. No backend, no spend.

The point under test is the chapter's load-bearing rule: every score is derived
from the **path** (which tools fired, the typed `MatchResult`), never the model's
prose. The trace sink is a recorder, so the thread key and the written scores are
asserted without an Opik server.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from autopilot import InvoiceId, MatchResult, PurchaseOrderId

from .feedback import derive_feedback, tools_fired
from .tracing import record_turn, thread_key


def _turn(fired: list[str], *, answer: str = "done") -> list[ModelMessage]:
    """A turn's messages: a user prompt, the model's tool calls, then its answer."""
    return [
        ModelRequest(parts=[UserPromptPart(content="Pay invoice INV-1043.")]),
        ModelResponse(parts=[ToolCallPart(tool_name=name, args={}) for name in fired]),
        ModelResponse(parts=[TextPart(content=answer)]),
    ]


def _matched(*, matched: bool) -> MatchResult:
    return MatchResult(
        invoice_id=InvoiceId("INV-1043"),
        matched=matched,
        purchase_order_id=PurchaseOrderId("PO-7781") if matched else None,
    )


class _RecordingSink:
    """Stands in for `opik.opik_context` — records what would hit the backend."""

    def __init__(self) -> None:
        self.thread_ids: list[str] = []
        self.tags: list[str] | None = None
        self.feedback_scores: list[dict[str, object]] | None = None

    def update_current_trace(
        self,
        *,
        thread_id: str | None = None,
        input: Mapping[str, object] | None = None,
        tags: list[str] | None = None,
        feedback_scores: list[dict[str, object]] | None = None,
    ) -> None:
        if thread_id is not None:
            self.thread_ids.append(thread_id)
        if tags is not None:
            self.tags = tags
        if feedback_scores is not None:
            self.feedback_scores = feedback_scores


# --- tools_fired reads the path, ignoring the prose --------------------------------


def test_tools_fired_collects_only_the_tool_calls_in_order() -> None:
    messages = _turn(["lookup_invoice", "match_to_po", "schedule_payment"])
    assert tools_fired(messages) == [
        "lookup_invoice",
        "match_to_po",
        "schedule_payment",
    ]


def test_tools_fired_ignores_tool_returns_and_text() -> None:
    # A ToolReturnPart also carries a tool_name; counting it would double the path.
    messages: list[ModelMessage] = [
        ModelResponse(parts=[ToolCallPart(tool_name="lookup_invoice", args={})]),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="lookup_invoice", content="{}", tool_call_id="c1"
                )
            ]
        ),
        ModelResponse(parts=[TextPart(content="It's within budget.")]),
    ]
    assert tools_fired(messages) == ["lookup_invoice"]  # the call, once


# --- scores are facts about what fired, not what the model said --------------------


def test_paid_is_true_because_schedule_payment_fired() -> None:
    payload = derive_feedback(
        fired=["lookup_invoice", "match_to_po", "schedule_payment"],
        match=_matched(matched=True),
    )
    by_name = {s.name: s.value for s in payload.scores}
    assert by_name["tool_called"] == 1.0
    assert by_name["paid"] == 1.0
    assert by_name["po_matched"] == 1.0


def test_a_cold_answer_with_no_tools_scores_all_zero() -> None:
    # Chapter 1's lie: the model answered from thin air. tool_called = 0 finds it.
    payload = derive_feedback(fired=[], match=None)
    by_name = {s.name: s.value for s in payload.scores}
    assert by_name["tool_called"] == 0.0
    assert by_name["paid"] == 0.0
    assert by_name["po_matched"] == 0.0


def test_the_incident_signature_paid_without_a_clean_match() -> None:
    # paid = 1 AND po_matched = 0 — the WHERE clause that finds the bad trace.
    payload = derive_feedback(
        fired=["lookup_invoice", "match_to_po", "schedule_payment"],
        match=_matched(matched=False),
    )
    by_name = {s.name: s.value for s in payload.scores}
    assert by_name["paid"] == 1.0
    assert by_name["po_matched"] == 0.0


# --- threading + the sink ----------------------------------------------------------


def test_thread_key_groups_a_turn_under_its_invoice_case() -> None:
    assert thread_key(InvoiceId("INV-1043")) == "invoice:INV-1043"


def test_record_turn_threads_then_writes_the_path_scores() -> None:
    sink = _RecordingSink()
    messages = _turn(["lookup_invoice", "match_to_po", "schedule_payment"])

    payload = record_turn(
        sink=sink,
        invoice_id=InvoiceId("INV-1043"),
        new_turn_messages=messages,
        match=_matched(matched=True),
    )

    # The trace is threaded under its invoice, and the indexed scores + tag land.
    assert sink.thread_ids == ["invoice:INV-1043"]
    assert sink.tags == ["ap"]
    assert sink.feedback_scores is not None
    written = {d["name"]: d["value"] for d in sink.feedback_scores}
    assert written == {"tool_called": 1.0, "paid": 1.0, "po_matched": 1.0}
    assert payload.score_dicts() == sink.feedback_scores
