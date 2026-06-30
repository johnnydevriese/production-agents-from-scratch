"""The tool menu this checkpoint presents to the model.

Chapter 3 (`ch03_tools`) *generates* these from the typed signatures in
`autopilot/tools.py`; this snapshot keeps the four read tools it actually
dispatches written out, so the chapter runs without reaching into another
checkpoint. The names match `DISPATCH` exactly — the string the model emits must
be a routable key — and the schemas ride along on *every* call, which is the
point of counting them in `window_tokens`.
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
        "name": "get_vendor",
        "description": "Fetch a vendor record by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {"vendor_id": {"type": "string"}},
            "required": ["vendor_id"],
        },
    },
    {
        "name": "match_to_po",
        "description": "Three-way match an invoice to its purchase order.",
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
]
