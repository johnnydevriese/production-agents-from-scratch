"""Durable execution: the flow that survives its own crash — modeled offline.

The invoice-to-pay flow spans a human wait (minutes, or days). No web request lives
that long; no in-memory loop survives a deploy. A durable-execution engine records
every completed step to a log and, on resume, **replays the log to rebuild state and
continues from the first step that hadn't finished** — completed steps are not re-run.
That one property makes the duplicate wire structurally impossible.

This module is a *teaching stand-in* for that engine (Temporal in production), not a
reimplementation: `DurableContext.execute_activity` records each result and replays it
on re-run instead of re-executing the side effect, and `wait_for_signal` is a
zero-cost suspend. It captures the single property that matters so the lesson runs
offline and deterministically. The real `@workflow.defn`/`execute_activity` wiring
against `temporal server start-dev` is in the `README`.

The hard split the engine enforces: **workflows are deterministic** (they only order
activities and await signals — `InvoiceToPayFlow.run` recomputes the idempotency key
the same way on every replay because it's a pure function of the invoice), and **all
side effects live in activities** (the rail, the ledger), which is exactly what lets
the engine record a result and skip the re-run.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, TypeVar

from pydantic import BaseModel, Field

from autopilot import (
    ApprovalRequest,
    Invoice,
    InvoiceId,
    JournalEntry,
    MatchResult,
    Payment,
    VendorId,
)

from .idempotency import payment_idempotency_key
from .rail import IdempotentRail

T = TypeVar("T", bound=BaseModel)


class ApprovalDenied(Exception):
    """The human rejected the payment. The flow stops; no money moves."""


class WorkflowSuspended(Exception):
    """Raised to suspend the workflow at a durable pause (awaiting a signal).

    The engine catches it; the history survives, so a resume re-runs nothing that
    already completed. In Temporal this is a zero-cost wait the engine holds on disk —
    a three-day wait and a three-second wait cost the same.
    """

    def __init__(self, signal_name: str) -> None:
        super().__init__(f"suspended awaiting signal {signal_name!r}")
        self.signal_name = signal_name


class WorkflowHistory(BaseModel):
    """The persistent log — the only state a resume needs.

    `results` maps a deterministic step id to the JSON of that activity's recorded
    result; `signals` holds delivered signal payloads. A crash loses the live flow
    object but not this log, so the engine replays it to rebuild state.
    """

    results: dict[str, str] = Field(default_factory=dict)
    signals: dict[str, bool] = Field(default_factory=dict)


class DurableContext:
    """A teaching stand-in for the engine's workflow context — replay-skip, no network.

    Records completed activities to `history` and replays them on re-run instead of
    re-executing, which is the single property that makes a crash a resume rather than
    a restart. `activity_runs` counts how many activities *actually* executed this run
    (vs. were replayed from the log) so a test can prove a completed step was skipped.
    """

    def __init__(self, history: WorkflowHistory) -> None:
        self.history = history
        self.activity_runs = 0

    def __repr__(self) -> str:
        return f"DurableContext(steps={len(self.history.results)}, ran_this_pass={self.activity_runs})"

    def execute_activity(
        self,
        step_id: str,
        activity: Callable[[], T],
        *,
        result_type: type[T],
    ) -> T:
        """Run an activity at most once across all replays.

        If its result is already in the history, return the recorded value WITHOUT
        re-running the side effect — that is how a crash after `schedule_payment`
        cannot pay twice. Otherwise run it, record the result, and return it.
        """
        recorded = self.history.results.get(step_id)
        if recorded is not None:
            return result_type.model_validate_json(
                recorded
            )  # replay: side effect skipped
        result = activity()  # first run: the side effect (rail, ledger) happens HERE
        self.history.results[step_id] = result.model_dump_json()
        self.activity_runs += 1
        return result

    def wait_for_signal(self, name: str) -> bool:
        """Suspend until the named signal is delivered. Raising `WorkflowSuspended` is
        the durable pause: the engine holds state and resumes when the signal lands."""
        if name not in self.history.signals:
            raise WorkflowSuspended(name)
        return self.history.signals[name]


class FlowOutcome(BaseModel):
    """The result of a (possibly partial) flow run — completed with a payment, or
    suspended at a durable pause awaiting a signal."""

    status: Literal["completed", "suspended"]
    payment: Payment | None = None
    awaiting_signal: str | None = None


class InvoiceToPayFlow:
    """The orchestration — deterministic, side-effect-free in its own body.

    It only orders activities and awaits the approval signal; every effect (the rail,
    the ledger) is delegated to an injected activity. The idempotency key is computed
    *inside* `run`, as a pure function of the invoice, so it replays identically.
    """

    def __init__(
        self,
        *,
        lookup: Callable[[InvoiceId], Invoice],
        match: Callable[[InvoiceId], MatchResult],
        vendor_account: Callable[[VendorId], str],
        rail: IdempotentRail,
    ) -> None:
        self._lookup = lookup
        self._match = match
        self._vendor_account = vendor_account
        self._rail = rail

    def run(self, ctx: DurableContext, invoice_id: InvoiceId) -> Payment:
        """One deterministic pass over the flow. Activities carry the side effects;
        a replay re-runs none that already completed."""
        invoice = ctx.execute_activity(
            "lookup_invoice", lambda: self._lookup(invoice_id), result_type=Invoice
        )
        match = ctx.execute_activity(
            "match_to_po", lambda: self._match(invoice_id), result_type=MatchResult
        )
        if match.discrepancies:
            ctx.execute_activity(
                "request_approval",
                lambda: ApprovalRequest(
                    invoice_id=invoice_id, reason="; ".join(match.discrepancies)
                ),
                result_type=ApprovalRequest,
            )
            approved = ctx.wait_for_signal("decision")  # durable pause — days are fine
            if not approved:
                raise ApprovalDenied(f"approver rejected payment for {invoice_id}")

        key = payment_idempotency_key(
            invoice
        )  # INSIDE the flow → recomputes identically on replay
        payment = ctx.execute_activity(
            "schedule_payment",
            lambda: self._pay(invoice, key),  # runs at most once across crashes
            result_type=Payment,
        )
        ctx.execute_activity(
            "post_journal_entry",
            lambda: _entry_for(payment),
            result_type=JournalEntry,
        )
        return payment

    def _pay(self, invoice: Invoice, key: str) -> Payment:
        resp = self._rail.transfer(
            account=self._vendor_account(invoice.vendor_id),
            amount=invoice.total,
            idempotency_key=key,  # the rail dedupes on this; a repeat is a no-op
        )
        return Payment(
            invoice_id=invoice.id,
            amount=invoice.total,
            idempotency_key=key,
            scheduled_for=resp.value_date,
        )


def _entry_for(payment: Payment) -> JournalEntry:
    return JournalEntry(
        invoice_id=payment.invoice_id,
        debit_account="2000-accounts-payable",
        credit_account="1000-cash",
        amount=payment.amount,
    )


def run_to_suspension(
    flow: InvoiceToPayFlow, ctx: DurableContext, invoice_id: InvoiceId
) -> FlowOutcome:
    """Drive the flow until it completes or hits a durable pause.

    On `WorkflowSuspended` the history is intact: deliver the signal into
    `ctx.history.signals` and call again to resume — completed activities replay, the
    now-satisfied wait passes, and the flow continues from where it stopped.
    """
    try:
        payment = flow.run(ctx, invoice_id)
        return FlowOutcome(status="completed", payment=payment)
    except WorkflowSuspended as exc:
        return FlowOutcome(status="suspended", awaiting_signal=exc.signal_name)
