"""Analyst-agent test — the verification loop, offline. Zero spend.

A `FunctionModel` scripts the trajectory: a buggy `run_python` (wrong column),
then a corrected one, then the answer. The sandbox is REAL — it runs both cells
in a child process — so the exit codes in the message history are real, not
mocked. We assert the agent looped (two calls) and that the environment handed
back the retry signal it loops on: a nonzero exit, then a clean one.

We can't test *that a real model reads stderr and decides to retry* offline —
that's model behavior. We test the machinery the decision rides on.
"""

from __future__ import annotations

from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .agent import analyst_agent
from .sandbox import RunPythonResult, SubprocessSandbox

_BUGGY = (
    "import polars as pl\n"
    "df = pl.read_parquet('invoices.parquet')\n"
    "print(df.group_by('vendor_id').agg(pl.col('amount').sum()))\n"
)
_FIXED = (
    "import polars as pl\n"
    "df = pl.read_parquet('invoices.parquet')\n"
    "print(df.group_by('vendor_id').agg(pl.col('total').sum().alias('cogs')))\n"
)


def _verification_loop_model() -> FunctionModel:
    """Buggy → corrected → report, keyed off how many results came back."""

    def model_fn(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        returns = sum(
            1
            for message in messages
            for part in getattr(message, "parts", [])
            if isinstance(part, ToolReturnPart) and part.tool_name == "run_python"
        )
        if returns == 0:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="run_python", args={"code": _BUGGY})]
            )
        if returns == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="run_python", args={"code": _FIXED})]
            )
        return ModelResponse(
            parts=[TextPart(content="COGS by vendor: V-ACME 2988.09.")]
        )

    return FunctionModel(model_fn)


def _run_python_exit_codes(messages: list[ModelMessage]) -> list[int]:
    return [
        part.content.exit_code
        for message in messages
        for part in getattr(message, "parts", [])
        if isinstance(part, ToolReturnPart)
        and part.tool_name == "run_python"
        and isinstance(part.content, RunPythonResult)
    ]


def test_a_nonzero_exit_drives_a_retry() -> None:
    with (
        SubprocessSandbox() as box,
        analyst_agent.override(model=_verification_loop_model()),
    ):
        result = analyst_agent.run_sync("COGS by vendor this quarter?", deps=box)

    tool_calls = [
        part
        for message in result.all_messages()
        for part in getattr(message, "parts", [])
        if isinstance(part, ToolCallPart) and part.tool_name == "run_python"
    ]
    assert len(tool_calls) == 2  # the agent retried

    # The sandbox produced a real failure, then a real success — the loop's fuel.
    exit_codes = _run_python_exit_codes(result.all_messages())
    assert exit_codes[0] != 0
    assert exit_codes[-1] == 0
    assert "v-acme" in result.output.lower()


def test_analyst_has_exactly_one_tool() -> None:
    # The whole bounded-vs-unbounded inversion, asserted: one tool, not seven.
    registered = set(analyst_agent._function_toolset.tools)  # pyright: ignore[reportPrivateUsage]
    assert registered == {"run_python"}
