"""The store roundtrip — money stays Decimal, a missing invoice raises. Real sqlite, no spend."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from autopilot import InvoiceId, InvoiceStatus, VendorId

from .store import Store, StoredInvoice, read_invoice, read_payment, seed_invoice


def _fresh_store(tmp_path: Path) -> Store:
    return Store(tmp_path / "ap.db")


def test_an_invoice_roundtrips_with_money_as_decimal_not_float(tmp_path: Path) -> None:
    store = _fresh_store(tmp_path)
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

    verify = store.connect()
    try:
        invoice = read_invoice(verify, InvoiceId("INV-1042"))
    finally:
        verify.close()
    assert invoice.total == Decimal("2988.09")
    assert isinstance(
        invoice.total, Decimal
    )  # text column → exact Decimal, never float
    assert invoice.status is InvoiceStatus.RECEIVED


def test_reading_a_missing_invoice_raises_rather_than_returning_none(
    tmp_path: Path,
) -> None:
    store = _fresh_store(tmp_path)
    conn = store.connect()
    try:
        with pytest.raises(KeyError):
            read_invoice(conn, InvoiceId("INV-DOES-NOT-EXIST"))
    finally:
        conn.close()


def test_an_unpaid_invoice_has_no_payment_row(tmp_path: Path) -> None:
    store = _fresh_store(tmp_path)
    conn = store.connect()
    try:
        seed_invoice(
            conn,
            StoredInvoice(
                id=InvoiceId("INV-1042"),
                vendor_id=VendorId("V-ACME"),
                total=Decimal("100.00"),
                due_date=date(2026, 7, 15),
                status=InvoiceStatus.RECEIVED,
            ),
        )
        conn.commit()
        # Absence is a legitimate queried state, not an error.
        assert read_payment(conn, InvoiceId("INV-1042")) is None
    finally:
        conn.close()
