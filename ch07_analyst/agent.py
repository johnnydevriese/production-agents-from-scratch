"""The analyst agent, wired with PydanticAI — one tool, unbounded by design.

Where the AP autopilot (Chapter 6) exposes seven typed tools, the analyst
exposes exactly one: `run_python`. The model decomposes the question, writes
Polars, reads the structured result, and retries on a nonzero exit. That loop —
not a fixed menu — is the agent.

    export ANTHROPIC_API_KEY=sk-...
    uv run python -m ch07_analyst.agent
"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext

from .sandbox import RunPythonResult, Sandbox
from .sandbox import run_python as _run_in_sandbox

analyst_agent = Agent(
    "anthropic:claude-sonnet-5",  # provider:model — same shape for openai:, google:
    deps_type=Sandbox,
    instructions=(
        "You are a finance analyst. Answer questions by writing Python that reads "
        "`invoices.parquet` — a polars-readable table of invoices — from your "
        "working directory. Plan first, then write code. Read the result: if "
        "exit_code is nonzero, fix the error shown in stderr and try again. Never "
        "report a number you did not compute; ground every figure in code output. "
        "The table's money column is `total`."
    ),
)


@analyst_agent.tool
def run_python(ctx: RunContext[Sandbox], code: str) -> RunPythonResult:
    """Run Python in the sandbox. Returns stdout, stderr, exit_code, artifacts."""
    return _run_in_sandbox(code, sandbox=ctx.deps)


def main() -> None:
    from .sandbox import SubprocessSandbox

    with SubprocessSandbox() as box:
        result = analyst_agent.run_sync(
            "What is total COGS by vendor this quarter? Show the top vendors.",
            deps=box,
        )
        print(result.output)


if __name__ == "__main__":
    main()
