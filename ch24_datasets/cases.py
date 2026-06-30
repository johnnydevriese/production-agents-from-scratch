"""The unit of a dataset: a typed case that cites its reason for existing.

A case is not a bare input string. It carries its **expected path**
(`expected_tools` / `forbidden_tools`, scored by Chapter 20's structural
assertions), its **answer constraints** (`answer_must_mention`, scored by Chapter
22's judge), and — the discipline this chapter is built on — its **provenance**:
why this case exists.

`guards` is the load-bearing field. It is required and non-empty by construction,
so *no case can enter the dataset without naming the failure it prevents*. "Pay a
clean invoice" is not a reason; "a PO-less EUR invoice pressed on to
schedule_payment instead of request_approval (prod incident 2026-06-23)" is. A
case whose `guards` you can't write is noise inflating your denominator.

`coverage` tags the matrix cell the case fills (see `coverage.py`) — coverage is
*cells filled*, not rows counted, so a case has to declare where it sits.
"""

from __future__ import annotations

from enum import Enum
from typing import Self

from pydantic import BaseModel, Field, model_validator

from autopilot import InvoiceId


class Origin(str, Enum):
    """Where a case came from. Drives trust and review cadence."""

    HANDWRITTEN = "handwritten"  # author imagined it
    REGRESSION = "regression"  # froze a real bug so it can't return
    MINED = "mined"  # lifted from a production trace (Ch 23)
    SYNTHETIC = "synthetic"  # generated to fill a coverage cell


class EvalCase(BaseModel):
    id: str
    request: str
    invoice_id: InvoiceId | None = None
    expected_tools: list[str]  # the golden PATH
    forbidden_tools: list[str] = Field(default_factory=list)  # acts that must NOT fire
    answer_must_mention: list[str] = Field(default_factory=list)

    origin: Origin
    guards: str = Field(min_length=1)  # the bug/surface this case exists to catch
    source_trace_id: str | None = None  # set when origin == MINED
    coverage: dict[str, str] = Field(default_factory=dict)  # the matrix cell it fills

    @model_validator(mode="after")
    def _mined_cases_cite_their_trace(self) -> Self:
        if self.origin is Origin.MINED and not self.source_trace_id:
            raise ValueError("a MINED case must cite its source_trace_id")
        return self
