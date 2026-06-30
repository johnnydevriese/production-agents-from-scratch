"""The bounded menu, as the provider needs to see it.

Chapter 2 hand-writes these two JSON-Schema descriptions so the shape is visible.
Chapter 3 (`ch03_tools`) generates them from the typed signatures in
`autopilot/tools.py` instead — hand-writing is the thing that doesn't scale.

Names match `AutopilotTools.lookup_invoice` / `.check_budget` exactly: the string
the model emits must be a key in the dispatch table, or the loop can't route it.
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
