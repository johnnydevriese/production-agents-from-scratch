"""The smallest possible agent: a single Anthropic Messages API call.

Run:
    export ANTHROPIC_API_KEY=sk-...
    uv run python summarize_invoice.py

The call shape is identical across providers (OpenAI, Gemini, Bedrock). Only the
client and the field names differ; the lesson transfers.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import anthropic
from anthropic.types import TextBlock

# A specific model ID dates badly — treat this as representative (see Appendix A).
MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = (
    "You are an accounts-payable assistant. Given the raw text of a vendor "
    "invoice, reply with a two-sentence summary: who is billing us, for how "
    "much, and when payment is due."
)


def summarize_invoice(invoice_text: str, *, client: anthropic.Anthropic) -> str:
    """Summarize one invoice. The model's only possible effect is returning text."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=200,        # ← a hard ceiling on the reply; the model stops here
        temperature=0,         # ← as close to deterministic as the API offers (see ch.)
        system=SYSTEM_PROMPT,  # ← steering, separate from the conversation
        messages=[{"role": "user", "content": invoice_text}],
    )
    # A no-tools reply is a single text block; the typed-block union is Chapter 2.
    return cast(TextBlock, response.content[0]).text


def main() -> None:
    invoice_text = Path("sample_invoice.txt").read_text()
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    response = client.messages.create(
        model=MODEL,
        max_tokens=200,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": invoice_text}],
    )

    # Everything the call gives back. There is no fourth thing.
    print("--- text ---")
    print(cast(TextBlock, response.content[0]).text)
    print("--- stop_reason ---")
    print(response.stop_reason)          # "end_turn" | "max_tokens" | ...
    print("--- usage ---")
    print(response.usage.input_tokens, "in /", response.usage.output_tokens, "out")


if __name__ == "__main__":
    main()
