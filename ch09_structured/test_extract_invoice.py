"""Offline tests for the forced-tool extractor. No network, no API key, zero spend.

The model never runs: a real `anthropic.Anthropic` has its `messages.create`
replaced with a function returning a fabricated `Message` that carries a single
`ToolUseBlock` — exactly the shape `tool_choice` guarantees. We assert (1) a typed
object crosses the boundary with `total` a `Decimal`, (2) the call forces the
emit-tool with the Pydantic schema, and (3) a malformed total dies AT the boundary.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import anthropic
import pytest
from anthropic.types import Message, ToolUseBlock, Usage
from pydantic import ValidationError

from autopilot.models import Invoice

from .extract_invoice import extract_invoice

VALID_INVOICE_ARGS: dict[str, Any] = {
    "id": "1043",
    "vendor_id": "acme-industrial",
    "purchase_order_id": "PO-2026-0517",
    "invoice_date": "2026-06-12",
    "due_date": "2026-07-12",
    "line_items": [
        {
            "description": "Hex bolts, M8 x 30mm (500 ct)",
            "quantity": 500,
            "unit_price": "1.68",
            "amount": "840.00",
        },
        {
            "description": "Pneumatic actuator",
            "quantity": 2,
            "unit_price": "950.00",
            "amount": "1900.00",
        },
        {
            "description": "Freight",
            "quantity": 1,
            "unit_price": "248.09",
            "amount": "248.09",
        },
    ],
    "subtotal": "2988.09",
    "tax": "0.00",
    "total": "2988.09",
    "status": "received",
}


def _client_emitting(
    tool_input: dict[str, Any],
) -> tuple[anthropic.Anthropic, list[dict[str, Any]]]:
    """A real client whose .messages.create returns one forced emit_invoice block."""
    client = anthropic.Anthropic(api_key="test-key-unused")
    calls: list[dict[str, Any]] = []

    def fake_create(**kwargs: Any) -> Message:
        calls.append(kwargs)
        return Message(
            id="msg_test",
            content=[
                ToolUseBlock(
                    id="toolu_test",
                    name="emit_invoice",
                    input=tool_input,
                    type="tool_use",
                )
            ],
            model="claude-sonnet-4-6",
            role="assistant",
            stop_reason="tool_use",
            stop_sequence=None,
            type="message",
            usage=Usage(input_tokens=10, output_tokens=5),
        )

    object.__setattr__(client.messages, "create", fake_create)
    return client, calls


def test_returns_a_typed_invoice_with_a_decimal_total() -> None:
    client, _calls = _client_emitting(VALID_INVOICE_ARGS)
    invoice = extract_invoice("…raw invoice text…", client=client)
    assert isinstance(invoice, Invoice)
    assert isinstance(invoice.total, Decimal)
    assert invoice.total == Decimal("2988.09")  # a number to compare, not a string


def test_forces_the_emit_tool_with_the_pydantic_schema() -> None:
    client, calls = _client_emitting(VALID_INVOICE_ARGS)
    extract_invoice("…raw invoice text…", client=client)
    assert len(calls) == 1  # one call — not the old summarize-then-reparse two
    (kwargs,) = calls
    assert kwargs["tool_choice"] == {"type": "tool", "name": "emit_invoice"}
    assert kwargs["tools"][0]["input_schema"] == Invoice.model_json_schema()


def test_a_malformed_total_dies_at_the_boundary() -> None:
    bad = {**VALID_INVOICE_ARGS, "total": "2,988.09"}  # the comma-decimal payment bug
    client, _calls = _client_emitting(bad)
    with pytest.raises(ValidationError):
        extract_invoice("…raw invoice text…", client=client)
