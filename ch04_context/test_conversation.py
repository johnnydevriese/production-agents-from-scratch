"""Offline tests for Chapter 4. No network, no API key, zero spend.

`messages.create` and `messages.count_tokens` are replaced with functions that
replay scripted values, and spans are captured by an in-memory exporter — so the
whole conversation-management story (accumulate, count, compact) and the first
span tree are asserted without touching a provider.
"""

from __future__ import annotations

import json
from typing import Any, cast

import anthropic
from anthropic.types import (
    Message,
    MessageParam,
    MessageTokensCount,
    TextBlock,
    ToolResultBlockParam,
    ToolUseBlock,
    Usage,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from .conversation import (
    COMPACT_THRESHOLD,
    compact_history,
    maybe_compact,
    run_turn,
    window_tokens,
)
from .tool_schemas import TOOLS
from .tools_impl import DISPATCH
from .tracing import agent_turn, configure_tracer, traced_dispatch


def _msg(*, stop_reason: str, blocks: list[TextBlock | ToolUseBlock]) -> Message:
    return Message(
        id="msg_test",
        content=list(blocks),
        model="claude-sonnet-5",
        role="assistant",
        stop_reason=stop_reason,  # pyright: ignore[reportArgumentType]
        stop_sequence=None,
        type="message",
        usage=Usage(input_tokens=10, output_tokens=5),
    )


def _text(text: str) -> TextBlock:
    return TextBlock(text=text, type="text", citations=None)


def _tool_use(name: str, args: dict[str, Any], *, block_id: str) -> ToolUseBlock:
    return ToolUseBlock(id=block_id, name=name, input=args, type="tool_use")


def _scripted_client(
    responses: list[Message], *, token_counts: list[int] | None = None
) -> tuple[anthropic.Anthropic, list[dict[str, Any]]]:
    client = anthropic.Anthropic(api_key="test-key-unused")
    pending = iter(responses)
    calls: list[dict[str, Any]] = []

    def fake_create(**kwargs: Any) -> Message:
        calls.append(kwargs)
        return next(pending)

    object.__setattr__(client.messages, "create", fake_create)

    if token_counts is not None:
        counts = iter(token_counts)

        def fake_count(**_kwargs: Any) -> MessageTokensCount:
            return MessageTokensCount(input_tokens=next(counts))

        object.__setattr__(client.messages, "count_tokens", fake_count)

    return client, calls


def _po_in(messages: list[MessageParam]) -> bool:
    """True if any tool_result in `messages` still carries the matched PO."""
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for raw in cast("list[object]", content):
            if not isinstance(raw, dict):
                continue  # skip pydantic tool_use/text blocks on assistant turns
            block = cast("dict[str, Any]", raw)
            if block.get("type") == "tool_result" and "PO-7781" in str(
                block.get("content")
            ):
                return True
    return False


def test_accumulation_carries_the_po_into_the_next_turn() -> None:
    client, calls = _scripted_client(
        [
            _msg(
                stop_reason="tool_use",
                blocks=[
                    _tool_use("match_to_po", {"invoice_id": "INV-1043"}, block_id="t1")
                ],
            ),
            _msg(
                stop_reason="end_turn", blocks=[_text("INV-1043 matched to PO-7781.")]
            ),
            _msg(stop_reason="end_turn", blocks=[_text("It matched to PO-7781.")]),
        ]
    )
    original: list[MessageParam] = []

    history = run_turn(
        "Look up INV-1043 and match it to its PO.",
        original,
        client=client,
        tools=TOOLS,
    )
    # The match result — PO-7781 — is in the accumulated history.
    assert _po_in(history)
    # We never mutated the caller's list (immutability by default).
    assert original == []

    run_turn("What PO did it match to?", history, client=client, tools=TOOLS)
    # Turn 2's request re-sent the whole transcript, PO included.
    assert _po_in(cast("list[MessageParam]", calls[-1]["messages"]))


def test_full_content_is_reappended_not_just_text() -> None:
    client, _calls = _scripted_client(
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

    history = run_turn("match INV-1043", [], client=client, tools=TOOLS)

    # The assistant turn that asked for a tool keeps its tool_use block — dropping
    # it (re-appending only .text) is the amnesia bug.
    assistant_blocks = [m["content"] for m in history if m["role"] == "assistant"]
    assert any(
        isinstance(c, list) and any(isinstance(b, ToolUseBlock) for b in c)
        for c in assistant_blocks
    )


def test_window_tokens_counts_tools_and_system() -> None:
    client, _calls = _scripted_client([], token_counts=[1180])
    captured: dict[str, Any] = {}

    def capture(**kwargs: Any) -> MessageTokensCount:
        captured.update(kwargs)
        return MessageTokensCount(input_tokens=1180)

    object.__setattr__(client.messages, "count_tokens", capture)

    n = window_tokens([{"role": "user", "content": "hi"}], client=client, tools=TOOLS)

    assert n == 1180
    assert captured["tools"] is TOOLS  # schemas are in the window
    assert "accounts-payable" in captured["system"]  # so is the system prompt


def _long_history_with_old_po() -> list[MessageParam]:
    """An old tool_result carrying PO-7781, then enough chatter to bury it."""
    match_result = json.dumps(
        {"invoice_id": "INV-1043", "matched": True, "purchase_order_id": "PO-7781"}
    )
    old_result: ToolResultBlockParam = {
        "type": "tool_result",
        "tool_use_id": "t1",
        "content": match_result,
    }
    history: list[MessageParam] = [
        {"role": "user", "content": "match INV-1043"},
        {"role": "user", "content": [old_result]},
    ]
    for i in range(10):
        history.append({"role": "assistant", "content": f"chatter {i}"})
        history.append({"role": "user", "content": f"more chatter {i}"})
    return history


def test_compaction_preserves_the_po_that_truncation_would_drop() -> None:
    history = _long_history_with_old_po()

    compacted = compact_history(history, keep_recent=4)

    # The naive move drops the head — and with it the PO.
    assert not _po_in(history[-4:]), "setup: a tail slice should NOT contain the PO"
    # Compaction keeps the fact by importance, not by position.
    summary = compacted[0]["content"]
    assert "PO-7781" in str(summary)
    assert len(compacted) < len(history)
    # First message is a user turn → the result is a sendable, alternating list.
    assert compacted[0]["role"] == "user"


def test_compaction_yields_alternating_roles() -> None:
    history = _long_history_with_old_po()
    compacted = compact_history(history, keep_recent=4)
    roles = [m["role"] for m in compacted]
    assert all(a != b for a, b in zip(roles, roles[1:])), roles


def test_maybe_compact_is_a_noop_below_threshold() -> None:
    client, _calls = _scripted_client([], token_counts=[COMPACT_THRESHOLD - 1])
    history = _long_history_with_old_po()

    result = maybe_compact(history, client=client, tools=TOOLS)

    assert result is history  # untouched: cheap common case


def test_maybe_compact_fires_above_threshold() -> None:
    client, _calls = _scripted_client([], token_counts=[COMPACT_THRESHOLD + 1])
    history = _long_history_with_old_po()

    result = maybe_compact(history, client=client, tools=TOOLS)

    assert len(result) < len(history)
    assert _po_in([result[0]]) or "PO-7781" in str(result[0]["content"])


def test_tool_spans_nest_under_the_turn_and_carry_the_risk_tier() -> None:
    exporter = InMemorySpanExporter()
    tracer = configure_tracer(exporter)
    client, _calls = _scripted_client(
        [
            _msg(
                stop_reason="tool_use",
                blocks=[
                    _tool_use("match_to_po", {"invoice_id": "INV-1043"}, block_id="t1")
                ],
            ),
            _msg(stop_reason="end_turn", blocks=[_text("matched")]),
        ]
    )

    with agent_turn(tracer, turn=1):
        run_turn(
            "match INV-1043",
            [],
            client=client,
            tools=TOOLS,
            dispatch=traced_dispatch(DISPATCH, tracer=tracer),
        )

    spans = exporter.get_finished_spans()
    by_name = {s.name: s for s in spans}
    assert "tool.match_to_po" in by_name
    assert "agent.turn" in by_name

    tool_span = by_name["tool.match_to_po"]
    assert tool_span.attributes is not None
    assert tool_span.attributes["tool.risk"] == "read_only"  # Ch 3 taxonomy
    assert tool_span.attributes["tool.matched"] is True
    # The tool span is a child of the turn span — a real trace tree.
    tool_parent = tool_span.parent
    turn_ctx = by_name["agent.turn"].context
    assert tool_parent is not None
    assert turn_ctx is not None
    assert tool_parent.span_id == turn_ctx.span_id


def test_chat_span_carries_the_gen_ai_conventions() -> None:
    exporter = InMemorySpanExporter()
    tracer = configure_tracer(exporter)
    client, _calls = _scripted_client(
        [_msg(stop_reason="end_turn", blocks=[_text("All set.")])]
    )

    with agent_turn(tracer, turn=1):
        run_turn("process INV-1043", [], client=client, tools=TOOLS, tracer=tracer)

    by_name = {s.name: s for s in exporter.get_finished_spans()}
    assert "gen_ai.chat" in by_name

    chat = by_name["gen_ai.chat"]
    assert chat.attributes is not None
    # Current gen_ai semantic conventions: provider.name, NOT the deprecated system.
    assert chat.attributes["gen_ai.provider.name"] == "anthropic"
    assert chat.attributes["gen_ai.request.model"] == "claude-sonnet-5"
    assert chat.attributes["gen_ai.usage.input_tokens"] == 10
    assert chat.attributes["gen_ai.usage.output_tokens"] == 5
    # The model-call span sits beside the tool spans, under the turn (Figure 4-2).
    chat_parent = chat.parent
    turn_ctx = by_name["agent.turn"].context
    assert chat_parent is not None
    assert turn_ctx is not None
    assert chat_parent.span_id == turn_ctx.span_id
