"""Offline tests for the triage pass. Pure — the queue is an in-memory recorder.

These pin that triage is data-driven (one row per filter), that a clean trace is
left alone while a smelly one is enqueued with its reasons, and that a batch
produces the flagged-ratio shape a human can actually work through.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from autopilot import InvoiceId, MatchResult, Payment, PurchaseOrderId
from autopilot.fixtures import INVOICES, VENDORS

from .models import Trace
from .triage import FILTERS, ListQueue, reasons_for, triage, triage_batch


def _clean_trace() -> Trace:
    invoice = INVOICES[InvoiceId("INV-1043")]
    vendor = VENDORS[invoice.vendor_id]
    return Trace(
        id="t-clean",
        request="Pay invoice INV-1043.",
        invoice=invoice,
        vendor=vendor,
        match=MatchResult(
            invoice_id=invoice.id,
            matched=True,
            purchase_order_id=PurchaseOrderId("PO-7781"),
        ),
        payment=Payment(
            invoice_id=invoice.id,
            amount=invoice.total,
            idempotency_key="k-1",
            scheduled_for=date(2026, 6, 30),
        ),
        tools_called=[
            "lookup_invoice",
            "get_vendor",
            "match_to_po",
            "check_budget",
            "schedule_payment",
        ],
        known_accounts=frozenset({vendor.bank_account}),
        po_total=invoice.total,
    )


def test_filters_are_a_data_driven_table() -> None:
    # Adding a check is one row, not an if/elif branch.
    assert set(FILTERS) == {"new_bank_account", "overpay", "missing_budget_check"}


def test_a_clean_trace_is_left_alone() -> None:
    queue = ListQueue()
    hits = triage(_clean_trace(), queue=queue)
    assert hits == []
    assert queue.items == []  # nothing for a human to look at


def test_the_phished_trace_is_flagged_and_enqueued() -> None:
    # The master Vendor record now holds an account we've never paid.
    phished = _clean_trace().model_copy(
        update={"id": "t-phish", "known_accounts": frozenset({"000-old-account"})}
    )
    queue = ListQueue()

    hits = triage(phished, queue=queue)

    assert "new_bank_account" in hits
    assert queue.items == [("t-phish", ["new_bank_account"])]


def test_a_trace_can_trip_multiple_filters() -> None:
    bad = _clean_trace().model_copy(
        update={
            "id": "t-bad",
            "known_accounts": frozenset({"000-old"}),  # new bank account
            "po_total": Decimal("100.00"),  # 2988.09 ≫ 3 × 100 → overpay
            "tools_called": [
                "lookup_invoice",
                "match_to_po",
                "schedule_payment",
            ],  # no budget
        }
    )
    hits = reasons_for(bad)
    assert set(hits) == {"new_bank_account", "overpay", "missing_budget_check"}


def test_triage_batch_reports_the_flagged_ratio() -> None:
    clean = [_clean_trace().model_copy(update={"id": f"ok-{i}"}) for i in range(20)]
    phished = _clean_trace().model_copy(
        update={"id": "t-phish", "known_accounts": frozenset({"000-old"})}
    )
    queue = ListQueue()

    report = triage_batch([*clean, phished], queue=queue)

    assert report.scanned == 21
    assert report.flagged == 1  # only the phished one smells
    assert report.reason_counts == {"new_bank_account": 1}
    assert len(queue.items) == 1  # the firehose became a one-item queue
