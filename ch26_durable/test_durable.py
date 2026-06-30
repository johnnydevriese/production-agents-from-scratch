"""The flow survives its own crash: completed activities replay, they never re-run.

These pin the chapter's headline — a crash after `schedule_payment` cannot pay twice
because the engine replays the recorded `Payment` instead of re-running the activity —
and the multi-day approval wait as a zero-cost suspend/resume. Offline teaching engine,
no Temporal server, no spend.
"""

from __future__ import annotations

import pytest

from autopilot import Invoice, InvoiceId, MatchResult, PurchaseOrderId
from autopilot.fixtures import INVOICES

from .durable import (
    ApprovalDenied,
    DurableContext,
    InvoiceToPayFlow,
    WorkflowHistory,
    run_to_suspension,
)
from .idempotency import payment_idempotency_key
from .rail import IdempotentRail

_INVOICE = INVOICES[InvoiceId("INV-1043")]


class _Lookups:
    """Injected activities with a call counter, so a test can prove replay-skip."""

    def __init__(self, invoice: Invoice, *, discrepancies: list[str]) -> None:
        self._invoice = invoice
        self._discrepancies = discrepancies
        self.lookup_calls = 0

    def lookup(self, invoice_id: InvoiceId) -> Invoice:
        self.lookup_calls += 1
        return self._invoice

    def match(self, invoice_id: InvoiceId) -> MatchResult:
        return MatchResult(
            invoice_id=invoice_id,
            matched=not self._discrepancies,
            purchase_order_id=PurchaseOrderId("PO-1"),
            discrepancies=list(self._discrepancies),
        )


def _flow(lookups: _Lookups, rail: IdempotentRail) -> InvoiceToPayFlow:
    return InvoiceToPayFlow(
        lookup=lookups.lookup,
        match=lookups.match,
        vendor_account=lambda _vendor_id: "000123456789",
        rail=rail,
    )


def test_a_clean_invoice_flows_straight_to_a_single_payment() -> None:
    lookups = _Lookups(_INVOICE, discrepancies=[])
    rail = IdempotentRail()
    ctx = DurableContext(WorkflowHistory())

    payment = _flow(lookups, rail).run(ctx, _INVOICE.id)

    assert payment.invoice_id == _INVOICE.id
    assert payment.idempotency_key == payment_idempotency_key(
        _INVOICE
    )  # computed inside the flow
    assert rail.transfer_count == 1
    assert "post_journal_entry" in ctx.history.results  # the ledger step recorded too


def test_a_crash_after_payment_replays_it_and_never_pays_twice() -> None:
    lookups = _Lookups(_INVOICE, discrepancies=[])
    rail = IdempotentRail()
    history = WorkflowHistory()

    # First pass completes and records every activity to the durable log.
    _flow(lookups, rail).run(DurableContext(history), _INVOICE.id)
    assert rail.transfer_count == 1
    assert lookups.lookup_calls == 1

    # The worker "crashes" and resumes: a fresh context over the SAME history re-runs
    # the flow body, but every completed activity is replayed from the log.
    resume_ctx = DurableContext(history)
    replayed = _flow(lookups, rail).run(resume_ctx, _INVOICE.id)

    assert resume_ctx.activity_runs == 0  # nothing re-executed
    assert rail.transfer_count == 1  # the duplicate wire is structurally impossible
    assert lookups.lookup_calls == 1  # lookup was replayed, not called again
    assert replayed.idempotency_key == payment_idempotency_key(_INVOICE)


def test_a_discrepancy_suspends_on_a_durable_wait_then_resumes_on_the_signal() -> None:
    lookups = _Lookups(_INVOICE, discrepancies=["amount mismatch vs PO"])
    rail = IdempotentRail()
    history = WorkflowHistory()
    flow = _flow(lookups, rail)

    # The flow pauses awaiting the human — no payment yet, and the wait costs nothing.
    suspended = run_to_suspension(flow, DurableContext(history), _INVOICE.id)
    assert suspended.status == "suspended"
    assert suspended.awaiting_signal == "decision"
    assert rail.transfer_count == 0

    # The approver says yes (days later); deliver the signal and resume.
    history.signals["decision"] = True
    resumed = run_to_suspension(flow, DurableContext(history), _INVOICE.id)

    assert resumed.status == "completed"
    assert rail.transfer_count == 1
    assert lookups.lookup_calls == 1  # the pre-wait activities replayed, not re-ran


def test_a_rejected_approval_stops_the_flow_and_moves_no_money() -> None:
    lookups = _Lookups(_INVOICE, discrepancies=["vendor not on file"])
    rail = IdempotentRail()
    history = WorkflowHistory()
    history.signals["decision"] = False  # the human rejected it

    with pytest.raises(ApprovalDenied):
        _flow(lookups, rail).run(DurableContext(history), _INVOICE.id)

    assert rail.transfer_count == 0  # nothing moved
    assert "schedule_payment" not in history.results
