"""Run #4471, frozen as data: a run has a path and an answer, and they're separate.

Chapter 19's one runnable idea. An agent run has two independent properties — the
*path* (the work it did: the ordered tool calls and their arguments) and the
*answer* (the text it produced) — and a fluent answer can ride on top of a broken
path. Run #4471 paid the wrong vendor while reporting that it paid the right one;
here it is captured as data so the two properties can be checked apart.

This is the hand-built ancestor of Chapter 20's real ``SpanTree``: there the path
is a span tree captured from a live agent; here it is a literal, so the distinction
can be drawn before the machinery to record it exists. The canonical vendor is read
from the shared fixture, so the "truth" the path is judged against can't drift.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from autopilot import InvoiceId, VendorId
from autopilot.fixtures import INVOICES

_INVOICE = INVOICES[InvoiceId("INV-1043")]
CORRECT_VENDOR: VendorId = _INVOICE.vendor_id  # V-ACME — what lookup_invoice returns
WRONG_VENDOR = VendorId("V-ACMI")  # a real, different vendor; the one-character slip

# The fluent summary #4471 produced. Every fact a skimming reviewer checks is right;
# the one it omits — which account the money reached — is the one that matters.
_FLUENT_ANSWER = (
    "Paid invoice #1043 to Acme Industrial Supply Co. — $2,988.09, scheduled "
    "2026-07-12 under Net 30. Matched to PO #PO-7781; within the Engineering "
    "supplies budget ($1,011.91 remaining). Journal entry posted (Dr 5000 / Cr 2000)."
)


class ToolCall(BaseModel, frozen=True):
    """One recorded step of the path: the tool, its arguments, and what it returned.

    Args and results are plain string maps — Chapter 19 cares about the *shape* of a
    recorded call (a name, some arguments, a result you can read back), not the typed
    tool surface from Chapter 3. Chapter 20 replaces this with a real span.
    """

    tool: str
    args: dict[str, str] = Field(default_factory=dict)
    returned: dict[str, str] = Field(default_factory=dict)


class AgentRun(BaseModel, frozen=True):
    """A single run reduced to its two evaluable properties."""

    run_id: str
    path: tuple[ToolCall, ...]
    answer: str


def _path(*, paid_vendor: VendorId) -> tuple[ToolCall, ...]:
    """The INV-1043 path, parameterized by which vendor the money actually reached.

    Everything up to ``get_vendor`` is identical between the broken and correct runs;
    the only difference is the argument fat-fingered into ``get_vendor`` and carried
    into ``schedule_payment``.
    """
    return (
        ToolCall(
            tool="lookup_invoice",
            args={"invoice_id": "INV-1043"},
            returned={"vendor_id": CORRECT_VENDOR, "total": "2988.09"},
        ),
        ToolCall(
            tool="match_to_po",
            args={"invoice_id": "INV-1043"},
            returned={"matched": "True", "po": "PO-7781"},
        ),
        ToolCall(
            tool="check_budget",
            args={"department": "Engineering", "amount": "2988.09"},
            returned={"within_budget": "True", "remaining": "1011.91"},
        ),
        ToolCall(
            tool="get_vendor",
            args={"vendor_id": paid_vendor},
            returned={"vendor_id": paid_vendor},
        ),
        ToolCall(
            tool="schedule_payment",
            args={"invoice_id": "INV-1043", "vendor_id": paid_vendor},
            returned={"amount": "2988.09"},
        ),
    )


RUN_4471 = AgentRun(
    run_id="4471", path=_path(paid_vendor=WRONG_VENDOR), answer=_FLUENT_ANSWER
)
"""The dangerous run: a flawless answer over a broken path (paid V-ACMI, not V-ACME)."""

GOOD_RUN = AgentRun(
    run_id="4470", path=_path(paid_vendor=CORRECT_VENDOR), answer=_FLUENT_ANSWER
)
"""What #4471 should have been: the same answer, over a path that paid V-ACME."""
