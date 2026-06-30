"""A finished production trace and a human's verdict on it.

The filters and the promote arrow are pure functions over these. `Trace` carries
the recorded domain I/O the autopilot's span tree already holds (Ch 17) — the
`Invoice` that triggered the run, the `Vendor` `get_vendor` returned, the
`MatchResult`, the proposed `Payment`, and the tool path — plus two facts known at
triage time: the bank accounts previously paid for this vendor and the matched
PO's total. A `HumanVerdict` is what an analyst writes after reading that trace.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from autopilot import Invoice, MatchResult, Payment, Vendor


class Trace(BaseModel):
    """One finished run, with the tool I/O frozen for replay and triage."""

    id: str
    request: str
    invoice: Invoice
    vendor: Vendor
    match: MatchResult
    payment: Payment | None = None
    tools_called: list[str] = Field(default_factory=list)
    known_accounts: frozenset[str] = frozenset()  # accounts paid before for this vendor
    po_total: Decimal | None = None  # the matched PO's total, looked up at triage time


class Label(str, Enum):
    """An analyst's call on a flagged trace."""

    CORRECT = "correct"
    INCORRECT = "incorrect"
    NEEDS_POLICY = "needs-policy"


class HumanVerdict(BaseModel):
    """What the analyst specifies — the *correct* path, not what the trace did.

    `expected_tools` / `forbidden_tools` are the path the human says *should* have
    happened (the correction-as-signal), and `note` is the free-text reason that
    becomes the promoted case's provenance — required, so no case is promoted
    without citing why.
    """

    label: Label
    expected_tools: list[str]
    forbidden_tools: list[str] = Field(default_factory=list)
    note: str = Field(min_length=1)
