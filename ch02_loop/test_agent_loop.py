"""Offline tests for the Chapter 2 loop. No network, no API key, zero spend.

The client is a real `anthropic.Anthropic`, but `messages.create` is replaced
with a function that replays scripted `Message`s — so the loop runs against
deterministic, fabricated provider responses.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import anthropic
import pytest
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from .agent_loop import AgentError, run_agent
from .tools_impl import check_budget


def _msg(*, stop_reason: str, blocks: list[TextBlock | ToolUseBlock]) -> Message:
    """Build a real Message with the given content blocks and stop reason."""
    return Message(
        id="msg_test",
        content=list(blocks),
        model="claude-sonnet-4-6",
        role="assistant",
        stop_reason=stop_reason,  # pyright: ignore[reportArgumentType]
        stop_sequence=None,
        type="message",
        usage=Usage(input_tokens=10, output_tokens=5),
    )


def _tool_use(name: str, args: dict[str, Any], *, block_id: str) -> ToolUseBlock:
    return ToolUseBlock(id=block_id, name=name, input=args, type="tool_use")


def _scripted_client(
    responses: list[Message],
) -> tuple[anthropic.Anthropic, list[dict[str, Any]]]:
    """A real client whose .messages.create replays `responses` in order.

    Returns the client and the live list of kwargs each create call received.
    """
    client = anthropic.Anthropic(api_key="test-key-unused")
    pending = iter(responses)
    calls: list[dict[str, Any]] = []

    def fake_create(**kwargs: Any) -> Message:
        calls.append(kwargs)
        return next(pending)

    object.__setattr__(client.messages, "create", fake_create)
    return client, calls


def _turn_has_tool_result(messages: list[dict[str, Any]]) -> bool:
    """True if any user turn carries a tool_result block back to the model."""
    for message in messages:
        content = message.get("content")
        if message.get("role") == "user" and isinstance(content, list):
            blocks = cast("list[dict[str, Any]]", content)
            if any(block.get("type") == "tool_result" for block in blocks):
                return True
    return False


def test_loop_grounds_answer_in_real_tool_results() -> None:
    client, calls = _scripted_client(
        [
            _msg(
                stop_reason="tool_use",
                blocks=[
                    _tool_use(
                        "lookup_invoice", {"invoice_id": "INV-1043"}, block_id="t1"
                    )
                ],
            ),
            _msg(
                stop_reason="tool_use",
                blocks=[
                    _tool_use(
                        "check_budget",
                        {"department": "Engineering", "amount": "2988.09"},
                        block_id="t2",
                    )
                ],
            ),
            _msg(
                stop_reason="end_turn",
                blocks=[
                    TextBlock(
                        text="Invoice INV-1043 is within budget, leaving $1,011.91.",
                        type="text",
                        citations=None,
                    )
                ],
            ),
        ]
    )

    answer = run_agent(
        "Is invoice INV-1043 within the Engineering department's budget?",
        client=client,
    )

    assert "within budget" in answer
    assert len(calls) == 3
    # The second call must carry the first tool's result back to the model.
    second_turn = cast("list[dict[str, Any]]", calls[1]["messages"])
    assert _turn_has_tool_result(second_turn)


def test_loop_caps_runaway_with_agent_error() -> None:
    client, _calls = _scripted_client(
        [
            _msg(
                stop_reason="tool_use",
                blocks=[
                    _tool_use(
                        "lookup_invoice", {"invoice_id": "INV-1043"}, block_id="t"
                    )
                ],
            )
        ]
        * 5
    )
    with pytest.raises(AgentError):
        run_agent("never finishes", client=client, max_steps=3)


def test_check_budget_produces_the_chapters_figure() -> None:
    result = check_budget(department="Engineering", amount=Decimal("2988.09"))
    assert result.within_budget is True
    assert result.budget_remaining == Decimal("1011.91")
