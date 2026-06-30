"""Generate the provider tool schemas from the typed signatures — not by hand.

Chapter 2 hand-wrote two JSON-Schema blocks so the shape was visible. That does
not scale to seven tools that each carry typed domain arguments, so here we
*derive* the schema from `AutopilotTools` (in `autopilot/tools.py`): one schema
per method, argument types read straight off the signature.

The *structure* (name, argument types, what's required) comes from the
signature. The *description* does not — it's prompt code, tuned like a prompt
(Chapter 8), so it lives in a separate table the model reads.
"""

from __future__ import annotations

import inspect
from decimal import Decimal
from typing import Any, cast, get_type_hints

from anthropic.types import ToolParam
from pydantic import BaseModel

from autopilot.tools import AutopilotTools

# How a Python parameter type maps to a JSON-Schema fragment the model fills in.
# Note `amount: Decimal` -> "string": money crosses the model boundary as an exact
# decimal string, then Pydantic validates it into the ledger type.
_PRIMITIVE_SCHEMA: dict[type, dict[str, str]] = {
    str: {"type": "string"},
    float: {"type": "number"},
    int: {"type": "integer"},
    bool: {"type": "boolean"},
    Decimal: {"type": "string"},
}

# Tool descriptions are prompt code (Chapter 8), kept apart from the structure.
TOOL_DESCRIPTIONS: dict[str, str] = {
    "lookup_invoice": "Fetch an invoice record by its ID. Read-only.",
    "get_vendor": "Fetch a vendor's master record by its ID. Read-only.",
    "match_to_po": "Three-way match an invoice against its purchase order. Read-only.",
    "check_budget": "Check whether an amount fits a department's remaining budget.",
    "request_approval": "Ask a human approver to sign off on an invoice before payment.",
    "schedule_payment": "Schedule payment of an invoice. Moves money; idempotent by key.",
    "post_journal_entry": "Post a journal entry to the general ledger. Irreversible.",
}


def _fragment_for(annotation: Any) -> dict[str, Any]:
    """JSON-Schema fragment for one parameter type. NewTypes unwrap to their base."""
    resolved: Any = annotation
    while getattr(resolved, "__supertype__", None) is not None:
        resolved = resolved.__supertype__
    if isinstance(resolved, type) and issubclass(resolved, BaseModel):
        return resolved.model_json_schema()
    fragment = _PRIMITIVE_SCHEMA.get(resolved)
    if fragment is None:
        raise TypeError(f"no JSON-Schema mapping for parameter type {annotation!r}")
    return dict(fragment)


def build_tool_schemas(
    protocol: type, descriptions: dict[str, str]
) -> list[ToolParam]:
    """One ToolParam per method on `protocol`, derived from its typed signature."""
    tools: list[ToolParam] = []
    for name, member in vars(protocol).items():
        if name.startswith("_") or not inspect.isfunction(member):
            continue
        hints = get_type_hints(member)
        properties: dict[str, Any] = {}
        required: list[str] = []
        for param in inspect.signature(member).parameters:
            if param == "self":
                continue
            properties[param] = _fragment_for(hints[param])
            required.append(param)
        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,  # reject args we didn't ask for
        }
        tools.append(
            cast(
                "ToolParam",
                {
                    "name": name,
                    "description": descriptions[name],
                    "input_schema": schema,
                },
            )
        )
    return tools


TOOLS: list[ToolParam] = build_tool_schemas(AutopilotTools, TOOL_DESCRIPTIONS)
