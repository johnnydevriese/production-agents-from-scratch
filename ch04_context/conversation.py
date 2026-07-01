"""Owning the working memory: accumulate, count, then compact on purpose.

The model is stateless (Chapter 1). Memory exists only because we re-send the
transcript. This module is the small, explicit manager around that `messages`
list — the three moves of Chapter 4:

* **accumulate** — `run_turn` appends the *full* `response.content` (text **and**
  `tool_use` blocks) every turn, so turn 2 still sees what turn 1 established.
* **count** — `window_tokens` asks the model's own tokenizer how big the next
  request is, schemas and system prompt included.
* **compact** — `maybe_compact`/`compact_history` shed tokens *by importance*,
  preserving the load-bearing facts a later `schedule_payment` needs, never by
  slicing the oldest messages off the front.

Run it for real:
    export ANTHROPIC_API_KEY=sk-...
    uv run python -m ch04_context.conversation
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

import anthropic
from anthropic.types import (
    ContentBlock,
    Message,
    MessageParam,
    TextBlockParam,
    ToolParam,
    ToolResultBlockParam,
    ToolUseBlock,
)
from opentelemetry import trace
from pydantic import BaseModel

from .tools_impl import DISPATCH
from .tracing import run_chat_span

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-5"  # representative; real IDs live in Appendix A

SYSTEM_PROMPT = (
    "You are an accounts-payable assistant. You have tools to look up invoices, "
    "match them to purchase orders, and check department budgets. When a question "
    "needs a fact, call the tool for it rather than guessing."
)

COMPACT_THRESHOLD = 8_000  # well under the model's limit; leave room to reply

# A wrong-typed argument is our bug, not an observation for the model.
_TOOL_FAILURES = (LookupError, ValueError)


def run_turn(
    user_text: str,
    history: Sequence[MessageParam],
    *,
    client: anthropic.Anthropic,
    tools: list[ToolParam],
    dispatch: Mapping[str, Callable[..., BaseModel]] = DISPATCH,
    tracer: trace.Tracer | None = None,
) -> list[MessageParam]:
    """Append one user turn, run the loop to completion, return the new history.

    `history` is the agent's entire working memory. We never mutate the caller's
    list in place — we build and return a new one (immutability by default). Pass a
    `tracer` to wrap each model call in a `gen_ai.chat` span (Chapter 4's first span
    tree); leave it `None` and the loop runs untraced.
    """
    messages: list[MessageParam] = [
        *history,
        {"role": "user", "content": user_text},
    ]

    def call_model() -> Message:
        return client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

    while True:
        response = (
            call_model()
            if tracer is None
            else run_chat_span(tracer, call_model, model=MODEL)
        )
        # Append the FULL content (text + tool_use blocks), not just the text.
        # Drop the tool_use blocks here and turn 2 forgets which PO matched.
        messages = [
            *messages,
            cast(MessageParam, {"role": "assistant", "content": response.content}),
        ]

        if response.stop_reason != "tool_use":
            return messages  # the loop from Chapter 2; tools are run inside it

        tool_results = run_tools(response.content, dispatch=dispatch)
        messages = [*messages, {"role": "user", "content": tool_results}]


def run_tools(
    blocks: Sequence[ContentBlock],
    *,
    dispatch: Mapping[str, Callable[..., BaseModel]],
) -> list[ToolResultBlockParam]:
    """Run every tool_use block in one assistant turn (the Chapter 3 dispatch)."""
    results: list[ToolResultBlockParam] = []
    for block in blocks:
        if not isinstance(block, ToolUseBlock):
            continue
        func = dispatch.get(block.name)
        if func is None:
            results.append(_tool_error(block.id, f"tool not available: {block.name}"))
            continue
        args = cast("dict[str, Any]", block.input)
        try:
            output = func(**args)
        except _TOOL_FAILURES as exc:
            results.append(_tool_error(block.id, f"{type(exc).__name__}: {exc}"))
            continue
        results.append(
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output.model_dump_json(),
            }
        )
    return results


def _tool_error(tool_use_id: str, message: str) -> ToolResultBlockParam:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": message,
        "is_error": True,
    }


def window_tokens(
    messages: Sequence[MessageParam],
    *,
    client: anthropic.Anthropic,
    tools: list[ToolParam],
) -> int:
    """The authoritative size of the next request, per the model's own tokenizer.

    Counts the tool schemas and the system prompt too — both ride along on every
    call, before the conversation says a word. A hand-rolled word count misses them.
    """
    count = client.messages.count_tokens(
        model=MODEL,
        system=SYSTEM_PROMPT,
        tools=tools,
        messages=messages,
    )
    return count.input_tokens


def maybe_compact(
    messages: list[MessageParam],
    *,
    client: anthropic.Anthropic,
    tools: list[ToolParam],
    keep_recent: int = 4,
) -> list[MessageParam]:
    """Compact only when the window crosses the threshold; otherwise do nothing."""
    if window_tokens(messages, client=client, tools=tools) < COMPACT_THRESHOLD:
        return messages  # cheap common case
    return compact_history(messages, keep_recent=keep_recent)


def compact_history(
    messages: Sequence[MessageParam], *, keep_recent: int = 4
) -> list[MessageParam]:
    """Shed tokens by importance, never by position.

    The naive `messages[-keep_recent:]` slice drops the *oldest* messages — which
    are exactly the ones carrying the durable facts (the original lookup, the PO
    match). Instead we mine the load-bearing facts out of the whole transcript,
    fold them into one compact summary, and keep that plus the recent tail. The
    `PO-7781` fact survives even though the message that first carried it is gone.

    A production system can have a cheap model *write* the summary; the principle
    the code encodes — select what to keep by importance — is the same either way.
    """
    if len(messages) <= keep_recent:
        return list(messages)

    facts = _durable_facts(messages[:-keep_recent])
    if not facts:
        return list(messages)  # nothing load-bearing to preserve; leave it alone

    summary = (
        "[Earlier turns compacted. Established facts:\n"
        + "\n".join(f"- {fact}" for fact in facts)
        + "\n]"
    )
    return _prepend_user_summary(summary, list(messages[-keep_recent:]))


def _durable_facts(messages: Sequence[MessageParam]) -> list[str]:
    """Extract the facts a later money-movement step would need to justify itself.

    Reads the structured `tool_result` payloads (each is a model's JSON dump) and
    keeps the ones that ground a payment: a matched PO, an invoice total.
    """
    facts: list[str] = []
    seen: set[str] = set()
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for raw in cast("list[object]", content):
            # tool_result blocks are dicts we built; assistant turns also carry
            # pydantic tool_use/text blocks — those aren't facts, so skip them.
            if not isinstance(raw, dict):
                continue
            block = cast("dict[str, Any]", raw)
            if block.get("type") != "tool_result" or block.get("is_error"):
                continue
            line = _fact_from_payload(block.get("content"))
            if line is not None and line not in seen:
                seen.add(line)
                facts.append(line)
    return facts


def _fact_from_payload(payload: object) -> str | None:
    if not isinstance(payload, str):
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    record = cast("dict[str, Any]", data)
    if record.get("purchase_order_id") and record.get("matched"):
        return f"{record['invoice_id']} matched to {record['purchase_order_id']}"
    if "total" in record and "id" in record:
        return f"invoice {record['id']} total {record['total']}"
    return None


def _prepend_user_summary(summary: str, tail: list[MessageParam]) -> list[MessageParam]:
    """Put the summary at the head as a user turn, keeping roles alternating.

    If the recent tail already opens with a user message, merge the summary into
    it rather than emitting two user messages in a row (which the API rejects).
    """
    summary_block: TextBlockParam = {"type": "text", "text": summary}
    if tail and tail[0]["role"] == "user":
        first, *rest = tail
        merged = [summary_block, *_as_blocks(first["content"])]
        return [{"role": "user", "content": merged}, *rest]
    return [{"role": "user", "content": [summary_block]}, *tail]


def _as_blocks(content: object) -> list[Any]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return cast("list[Any]", content)
    return [content]


def main() -> None:
    from .tool_schemas import TOOLS

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tools = TOOLS
    history = run_turn(
        "Look up invoice INV-1043 and match it to its PO.",
        [],
        client=client,
        tools=tools,
    )
    history = run_turn(
        "Good — what was the PO it matched to?", history, client=client, tools=tools
    )
    final = history[-1]
    logger.info("final turn: %s", final)
    print(f"window now: {window_tokens(history, client=client, tools=tools)} tokens")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
