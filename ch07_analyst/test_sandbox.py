"""Sandbox tests — real subprocess execution, no LLM, no spend.

These prove the trust boundary's *behavior*: model code runs in a CHILD process
(a `sys.exit` there doesn't take us down), the verification loop's signals are
real (`exit_code`/`stderr` from an actual run, not a mock), and the workspace is
ephemeral. The two query bodies are the chapter's exact trajectory.
"""

from __future__ import annotations

from .sandbox import SubprocessSandbox, run_python

_BUGGY = (
    "import polars as pl\n"
    "df = pl.read_parquet('invoices.parquet')\n"
    "print(df.group_by('vendor_id').agg(pl.col('amount').sum()))\n"  # wrong column
)
_FIXED = (
    "import polars as pl\n"
    "df = pl.read_parquet('invoices.parquet')\n"
    "print(df.group_by('vendor_id').agg(pl.col('total').sum().alias('cogs')))\n"
)


def test_clean_run_captures_stdout_and_exits_zero() -> None:
    with SubprocessSandbox() as box:
        result = run_python("print('hello from the box')", sandbox=box)
    assert result.exit_code == 0
    assert "hello from the box" in result.stdout
    assert result.stderr == ""


def test_the_wrong_column_is_a_real_retry_signal() -> None:
    # Step 1 of the chapter's trajectory: `amount` is a line-item field, not a
    # column on the invoice-level table → ColumnNotFoundError, nonzero exit.
    with SubprocessSandbox() as box:
        result = run_python(_BUGGY, sandbox=box)
    assert result.exit_code != 0
    assert "ColumnNotFound" in result.stderr
    assert result.stdout == ""


def test_the_corrected_query_runs_clean_over_the_seeded_invoices() -> None:
    # Step 2: `amount` → `total`. Exit zero, real numbers to report.
    with SubprocessSandbox() as box:
        result = run_python(_FIXED, sandbox=box)
    assert result.exit_code == 0
    assert "V-ACME" in result.stdout
    assert result.stderr == ""


def test_model_code_runs_in_a_child_not_our_interpreter() -> None:
    # `sys.exit(3)` in model code must NOT kill the test process — proof it ran
    # in a child, not via exec() in-process. We live to observe the child's code.
    with SubprocessSandbox() as box:
        result = run_python("import sys; sys.exit(3)", sandbox=box)
    assert result.exit_code == 3


def test_files_the_code_writes_show_up_as_artifacts() -> None:
    with SubprocessSandbox() as box:
        result = run_python(
            "from pathlib import Path; Path('report.txt').write_text('done')",
            sandbox=box,
        )
    assert "report.txt" in result.artifacts


def test_a_runaway_hits_the_wall_clock_cap() -> None:
    with SubprocessSandbox(timeout_s=0.5) as box:
        result = run_python("while True:\n    pass\n", sandbox=box)
    assert result.exit_code != 0  # not a clean success
    assert "timeout" in result.stderr.lower()


def test_workspace_is_ephemeral() -> None:
    box = SubprocessSandbox()
    workspace = box.workspace
    assert (workspace / "invoices.parquet").exists()  # seeded on construction
    box.close()
    assert not workspace.exists()  # thrown away after the task
