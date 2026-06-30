"""Risk-aware dispatch: name the danger, run the tool, never swallow a failure.

This is the one place Chapter 3 changes the loop. Before running a tool we log
its risk tier (the seed of every guardrail in Chapter 10). When a tool raises, we
do not crash the loop or drop the result — we return a `tool_result` flagged
`is_error` so the model sees the failure and can adapt. Dropping it would be the
`except: pass` the standards forbid.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from anthropic.types import ContentBlock, ToolResultBlockParam, ToolUseBlock
from pydantic import BaseModel

from .risk import describe_risk

logger = logging.getLogger(__name__)

# Tool failures we report back to the model. A wrong-typed argument (TypeError)
# is a bug in our code, not an observation for the model, so it still propagates.
_TOOL_FAILURES = (LookupError, ValueError)


def run_tool_calls(
    blocks: Sequence[ContentBlock],
    *,
    dispatch: Mapping[str, Callable[..., BaseModel]],
) -> list[ToolResultBlockParam]:
    """Run every tool_use block in one assistant turn; return all the results."""
    results: list[ToolResultBlockParam] = []
    for block in blocks:
        if not isinstance(block, ToolUseBlock):
            continue
        func = dispatch.get(block.name)
        if func is None:
            results.append(_error(block.id, f"tool not available: {block.name}"))
            continue
        logger.info("about to run %s", describe_risk(block.name))  # risk before run
        args = cast("dict[str, Any]", block.input)
        try:
            output = func(**args)
        except _TOOL_FAILURES as exc:
            results.append(_error(block.id, f"{type(exc).__name__}: {exc}"))
            continue
        results.append(
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output.model_dump_json(),
            }
        )
    return results


def _error(tool_use_id: str, message: str) -> ToolResultBlockParam:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": message,
        "is_error": True,
    }
