"""The transaction boundary, proven over a SECOND connection — the test the dict couldn't be.

This is the full-stack lane (`full_stack_eval`): a real database, the real boundary,
and a fresh connection to read the effect back. The contrast with Chapter 20 is the
whole chapter — Ch 20 asserts the span fired (the path); these assert the row is
visible (the effect). A green span and a missing row is the cold-open bug, and only
the second-connection read can see it. No model, no network, no spend.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from autopilot import InvoiceId, InvoiceStatus, VendorId

from .boundary import run_turn, schedule_payment
from .store import Store, StoredInvoice, read_invoice, read_payment, seed_invoice


def _seeded_store(tmp_path: Path) -> Store:
    """A real DB with INV-1042 in status RECEIVED, committed and durable."""
    store = Store(tmp_path / "ap.db")
    conn = store.connect()
    try:
        seed_invoice(
            conn,
            StoredInvoice(
                id=InvoiceId("INV-1042"),
                vendor_id=VendorId("V-ACME"),
                total=Decimal("2988.09"),
                due_date=date(2026, 7, 15),
                status=InvoiceStatus.RECEIVED,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return store


@pytest.mark.full_stack_eval
def test_a_scheduled_payment_is_visible_on_a_second_connection(tmp_path: Path) -> None:
    store = _seeded_store(tmp_path)

    run_turn(
        store,
        lambda conn: schedule_payment(
            conn, InvoiceId("INV-1042"), idempotency_key="k-1"
        ),
    )

    verify = store.connect()  # a different connection — does the commit reach it?
    try:
        invoice = read_invoice(verify, InvoiceId("INV-1042"))
        assert invoice.status is InvoiceStatus.SCHEDULED  # was RECEIVED before the turn
        assert (
            read_payment(verify, InvoiceId("INV-1042")) is not None
        )  # the row reached disk
    finally:
        verify.close()


@pytest.mark.full_stack_eval
def test_a_failed_turn_commits_nothing_even_though_the_tool_ran(tmp_path: Path) -> None:
    store = _seeded_store(tmp_path)

    def work(conn: sqlite3.Connection) -> None:
        schedule_payment(
            conn, InvoiceId("INV-1042"), idempotency_key="k-1"
        )  # the tool ran — a span would fire
        raise RuntimeError(
            "model raised after the tool call (or the stream disconnected)"
        )

    with pytest.raises(RuntimeError):
        run_turn(store, work)

    verify = store.connect()
    try:
        # The cold-open bug, reproduced as a passing test: 'Decided' and 'Executed'
        # both happened, but nothing was 'Committed', so nothing is 'Visible'.
        assert (
            read_invoice(verify, InvoiceId("INV-1042")).status is InvoiceStatus.RECEIVED
        )
        assert read_payment(verify, InvoiceId("INV-1042")) is None
    finally:
        verify.close()


def test_a_replay_with_the_same_idempotency_key_never_pays_twice(
    tmp_path: Path,
) -> None:
    store = _seeded_store(tmp_path)

    run_turn(
        store,
        lambda c: schedule_payment(c, InvoiceId("INV-1042"), idempotency_key="k-1"),
    )
    # The same key again: the UNIQUE constraint trips and the boundary rolls the turn back.
    with pytest.raises(sqlite3.IntegrityError):
        run_turn(
            store,
            lambda c: schedule_payment(c, InvoiceId("INV-1042"), idempotency_key="k-1"),
        )

    verify = store.connect()
    try:
        row = verify.execute(
            "SELECT COUNT(*) AS n FROM payments WHERE invoice_id = ?",
            ("INV-1042",),
        ).fetchone()
        assert row["n"] == 1  # exactly one payment, despite two attempts
    finally:
        verify.close()
