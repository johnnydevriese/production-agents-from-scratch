"""Two checks over a run — one per property. This is Chapter 19, made executable.

``answer_cites_invoice`` reads only the final text, the way a reviewer skimming the
chat does. ``payment_matches_lookup`` ignores the text and asserts on the path: the
vendor the money reached must be the vendor the invoice lookup returned. On run
#4471 the first passes and the second fails — proof that an answer check and a path
check are different instruments measuring different properties.
"""

from __future__ import annotations

from pydantic import BaseModel

from .run import AgentRun, ToolCall


class CheckResult(BaseModel, frozen=True):
    passed: bool
    detail: str


def _first_call(run: AgentRun, tool: str) -> ToolCall:
    for call in run.path:
        if call.tool == tool:
            return call
    raise LookupError(f"run {run.run_id} never called {tool!r}")


def answer_cites_invoice(
    run: AgentRun, *, invoice_number: str, amount: str
) -> CheckResult:
    """Answer-only check: does the summary name the right invoice and total?

    This is the check a human skimming the chat applies — and it stamps #4471 green.
    """
    cited = invoice_number in run.answer and amount in run.answer
    verb = "cites" if cited else "omits"
    return CheckResult(
        passed=cited, detail=f"answer {verb} {invoice_number} and {amount}"
    )


def payment_matches_lookup(run: AgentRun) -> CheckResult:
    """Path assertion: the vendor the payment resolved to must equal the vendor the
    lookup returned.

    Reads nothing from the answer. ``schedule_payment`` takes only an invoice id, so
    the account the money reaches is decided by the ``get_vendor`` call that resolves
    it — that argument is what we check. On #4471 lookup returned V-ACME but
    ``get_vendor`` was called with V-ACMI, so this fails on exactly the run the answer
    check waved through.
    """
    looked_up = _first_call(run, "lookup_invoice").returned["vendor_id"]
    paid = _first_call(run, "get_vendor").args["vendor_id"]
    return CheckResult(
        passed=looked_up == paid,
        detail=f"lookup returned {looked_up}, payment resolved to {paid}",
    )
