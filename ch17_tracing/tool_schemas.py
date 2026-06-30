"""The bounded menu as the provider sees it — hand-written for the demo.

Chapter 3 generates these from the typed signatures; here we list the four tools
the traced loop's worked example walks through (read path + escalation) so a real
`uv run python -m ch17_tracing.traced_loop` has a menu to offer the model. The
offline tests script the model's tool calls directly, so they don't depend on
these.
"""

from __future__ import annotations

from anthropic.types import ToolParam

TOOLS: list[ToolParam] = [
    {
        "name": "lookup_invoice",
        "description": "Fetch an invoice record by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {"invoice_id": {"type": "string"}},
            "required": ["invoice_id"],
        },
    },
    {
        "name": "match_to_po",
        "description": "Three-way match an invoice against its purchase order.",
        "input_schema": {
            "type": "object",
            "properties": {"invoice_id": {"type": "string"}},
            "required": ["invoice_id"],
        },
    },
    {
        "name": "check_budget",
        "description": "Is this amount within a department's budget?",
        "input_schema": {
            "type": "object",
            "properties": {
                "department": {"type": "string"},
                "amount": {"type": "string"},
            },
            "required": ["department", "amount"],
        },
    },
    {
        "name": "request_approval",
        "description": "Escalate an invoice to a human approver with a reason.",
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["invoice_id", "reason"],
        },
    },
]
