"""Extract a typed, validated Invoice from raw vendor text — the model's 8th capability.

The chapter's strongest technique: hand the provider the Pydantic-generated JSON
schema and FORCE a tool call, so the decoder is constrained to schema-valid JSON.
The model's only move is to fill in `emit_invoice`'s arguments; we never run that
tool — its arguments ARE the output. Validating at the boundary means nothing
untyped leaks downstream into `check_budget` / `schedule_payment`.

`extract_invoice` is a model *capability*, not an eighth entry on the
`AutopilotTools` Protocol (still seven typed actions). It uses the raw provider SDK
directly — the Chapter 3 forced-tool machinery, repurposed so the tool is never run.

    export ANTHROPIC_API_KEY=sk-...
    uv run python -m ch09_structured.extract_invoice
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

import anthropic
from anthropic.types import MessageParam, ToolChoiceToolParam, ToolParam, ToolUseBlock

from autopilot.models import Invoice  # the frozen contract, unchanged since Ch 1

MODEL = "claude-sonnet-4-6"  # representative — see Appendix A

SYSTEM_PROMPT = (
    "You are an accounts-payable extractor. Read the raw invoice text and return "
    "the invoice as JSON matching the provided schema. Money fields are decimal "
    "numbers with no currency symbol or thousands separators. Dates are ISO-8601 "
    "(YYYY-MM-DD). If a field is genuinely absent, omit it; never guess a value."
)

EMIT_INVOICE: ToolParam = {
    "name": "emit_invoice",
    "description": "Return the parsed invoice.",
    "input_schema": cast("Any", Invoice.model_json_schema()),  # Pydantic owns the shape
}
FORCE_EMIT: ToolChoiceToolParam = {"type": "tool", "name": "emit_invoice"}


def extract_invoice(invoice_text: str, *, client: anthropic.Anthropic) -> Invoice:
    """Read raw invoice text → a validated Invoice. The schema is the boundary."""
    messages: list[MessageParam] = [{"role": "user", "content": invoice_text}]
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=messages,
        tools=[EMIT_INVOICE],
        tool_choice=FORCE_EMIT,  # the model may only reply by calling emit_invoice
    )
    # tool_choice forces exactly one tool block; its .input is our JSON object.
    emitted = next(b for b in response.content if isinstance(b, ToolUseBlock))
    # The boundary: nothing crosses into typed code until it validates.
    return Invoice.model_validate(emitted.input)


def main() -> None:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    text = (Path(__file__).parent / "sample_invoice.txt").read_text(encoding="utf-8")
    print(extract_invoice(text, client=client))


if __name__ == "__main__":
    main()
