"""The whole agent: a loop around the stateless model.

observe → think → act → observe. The model proposes tool calls; this code
disposes of them, runs them, and feeds the results back. Three stop conditions:
the model finishes, a hard step cap, or a raised error. Every step is printed —
crude on purpose; Chapter 4 turns these into OpenTelemetry spans.

Run it for real:
    export ANTHROPIC_API_KEY=sk-...
    uv run python -m ch02_loop.agent_loop
"""

from __future__ import annotations

import os
from typing import Any, cast

import anthropic
from anthropic.types import (
    Message,
    MessageParam,
    TextBlock,
    ToolResultBlockParam,
    ToolUseBlock,
)

from .tool_schemas import TOOLS
from .tools_impl import DISPATCH

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = (
    "You are an accounts-payable assistant. You have tools to look up invoices "
    "and check department budgets. When a question needs a fact, call the tool "
    "for it rather than guessing. Never invent an amount or a budget."
)


class AgentError(RuntimeError):
    """The loop could not finish — e.g. it hit the step cap without an answer."""


def run_agent(task: str, *, client: anthropic.Anthropic, max_steps: int = 8) -> str:
    """Run the observe→think→act→observe loop until the model stops or we cap it."""
    messages: list[MessageParam] = [{"role": "user", "content": task}]

    for step in range(max_steps):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        log_step(step, response)

        if response.stop_reason != "tool_use":
            return _final_text(response)

        # Remember exactly what the model asked for, paired by tool_use_id.
        messages.append(
            cast(MessageParam, {"role": "assistant", "content": response.content})
        )

        results: list[ToolResultBlockParam] = []
        for block in response.content:
            if not isinstance(block, ToolUseBlock):
                continue
            args = cast("dict[str, Any]", block.input)
            output = DISPATCH[block.name](**args)  # ACT: run the tool in our code
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output.model_dump_json(),
                }
            )
        messages.append({"role": "user", "content": results})  # OBSERVE: reality back in

    raise AgentError(f"did not finish within {max_steps} steps")


def _final_text(response: Message) -> str:
    """Concatenate the text blocks of a finished (non-tool_use) response."""
    return "".join(b.text for b in response.content if isinstance(b, TextBlock))


def log_step(step: int, response: Message) -> None:
    """Print one line per step: the stop reason and any tools the model requested."""
    print(f"[step {step}] stop_reason={response.stop_reason}")
    for block in response.content:
        if isinstance(block, ToolUseBlock):
            print(f"         ↳ tool_use {block.name} {block.input}")


def main() -> None:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    answer = run_agent(
        "Is invoice INV-1043 within the Engineering department's budget?",
        client=client,
    )
    print("--- answer ---")
    print(answer)


if __name__ == "__main__":
    main()
