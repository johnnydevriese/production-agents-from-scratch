"""The analyst's one tool — and the box it runs in.

The orchestration agent (Chapter 6) had seven typed tools; the analyst has one,
`run_python`, and its argument is *arbitrary source code* a probabilistic model
wrote. Everything dangerous lives in that `code: str`, so it never runs in our
interpreter — it runs in a child process, in an ephemeral workspace, under a
wall-clock cap.

What this checkpoint **is**: an honest version 0 — process isolation (a child,
not `exec`), a per-task workspace thrown away after use, captured
stdout/stderr/exit_code, a wall-clock timeout. What it is **not**: a security
boundary against hostile code. A child process can still reach the host
filesystem and the network. Production swaps `SubprocessSandbox` for the
containment the chapter's table specifies — a container or microVM, a network
namespace, seccomp, cgroup CPU/memory limits. The *interface* (`Sandbox.execute`)
and the verification loop it powers are identical at any level of containment;
only the strength of the box changes.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import TracebackType
from typing import Protocol, Self

import polars as pl
from pydantic import BaseModel

from autopilot.fixtures import INVOICES

_SEED_FILE = "invoices.parquet"
_TIMEOUT_EXIT = 124  # conventional "killed by timeout" code (matches GNU `timeout`)


class RunPythonResult(BaseModel):
    """What comes back from one execution. The model reads ALL of this."""

    stdout: str
    stderr: str
    exit_code: int  # 0 = success; nonzero is the retry signal
    artifacts: list[str]  # files the code wrote into the workspace


class Sandbox(Protocol):
    """The trust boundary. Implementations contain the code; they never trust it."""

    def execute(self, code: str) -> RunPythonResult: ...


def export_invoices_parquet(path: Path) -> Path:
    """Flatten the canonical invoices into the table the analyst queries.

    The same invoices the AP autopilot pays, sitting still to be queried. Money
    is downcast to float here — the analytics surface, not the ledger; the source
    of truth stays `Decimal` in `autopilot.models`. Note the column is `total`,
    not `amount`: reaching for `amount` (a *line-item* field) on this
    invoice-level table is the wrong-column bug the verification loop catches.
    """
    frame = pl.DataFrame(
        [
            {
                "invoice_id": str(inv.id),
                "vendor_id": str(inv.vendor_id),
                "status": inv.status.value,
                "subtotal": float(inv.subtotal),
                "tax": float(inv.tax),
                "total": float(inv.total),
            }
            for inv in INVOICES.values()
        ]
    )
    frame.write_parquet(path)
    return path


class SubprocessSandbox:
    """Runs model code in a child process, in an ephemeral seeded workspace.

    Use as a context manager so the workspace is always torn down::

        with SubprocessSandbox() as box:
            run_python("print('hi')", sandbox=box)
    """

    def __init__(self, *, timeout_s: float = 10.0) -> None:
        self._timeout_s = timeout_s
        self.workspace = Path(tempfile.mkdtemp(prefix="analyst-ws-"))
        export_invoices_parquet(self.workspace / _SEED_FILE)

    def __repr__(self) -> str:
        return f"SubprocessSandbox(workspace={self.workspace.name!r})"

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        shutil.rmtree(self.workspace, ignore_errors=True)

    def execute(self, code: str) -> RunPythonResult:
        before = {p.name for p in self.workspace.iterdir()}
        try:
            completed = subprocess.run(
                [sys.executable, "-c", code],  # a list, never shell=True
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return RunPythonResult(
                stdout="",
                stderr=f"TimeoutExpired: exceeded the {self._timeout_s}s wall-clock cap",
                exit_code=_TIMEOUT_EXIT,
                artifacts=[],
            )
        artifacts = sorted({p.name for p in self.workspace.iterdir()} - before)
        return RunPythonResult(
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
            artifacts=artifacts,
        )


def run_python(code: str, *, sandbox: Sandbox) -> RunPythonResult:
    """Execute model-written Python inside an isolated workspace.

    This is the entire bounded-vs-unbounded difference in one signature: the
    orchestration agent had seven typed tools; the analyst has one, and its
    argument is *arbitrary source code*. Everything dangerous about a coding
    agent lives in that `code: str` — which is why `sandbox` owns isolation.
    """
    return sandbox.execute(code)
