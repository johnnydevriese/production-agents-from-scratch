"""A real SQLite store — the subsystem the in-memory eval deletes.

The cold open's bug — *the span fired, the row never reached disk* — can only exist
where there is a transaction to leave half-open. A dict has none, so the fast unit
test is structurally blind to it. This module restores that subsystem with stdlib
`sqlite3` (no server): every `Store.connect()` is an independent connection with its
own transaction, so a write that has not been committed on one connection is
**invisible** to another. That invisibility is exactly the failure mode, and the
second-connection read in the eval is the only thing that can see it.

The store holds rows; it owns no transaction policy — `boundary.run_turn` decides
when work becomes durable. Reads return typed canon models, validated at the edge.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field

from autopilot import InvoiceId, InvoiceStatus, Payment, VendorId

_SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id          TEXT PRIMARY KEY,
    vendor_id   TEXT NOT NULL,
    total       TEXT NOT NULL,         -- Decimal as text: money never round-trips through float
    due_date    TEXT NOT NULL,         -- ISO date
    status      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
    invoice_id      TEXT NOT NULL,
    amount          TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,  -- the same key never pays twice (Chapter 26)
    scheduled_for   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    thread_id TEXT NOT NULL,
    seq       INTEGER NOT NULL,
    role      TEXT NOT NULL,
    content   TEXT NOT NULL,
    PRIMARY KEY (thread_id, seq)
);
CREATE TABLE IF NOT EXISTS vendor_memory (
    vendor_id        TEXT NOT NULL,
    preference       TEXT NOT NULL,
    source_thread_id TEXT,
    confidence       REAL NOT NULL,
    reviewed         INTEGER NOT NULL   -- governance: an unreviewed learning never graduates
);
"""


class StoredInvoice(BaseModel):
    """The persisted projection of an invoice — only what the ledger path needs.

    Not the full Chapter 2 `Invoice` (no line items): the store keeps the columns the
    money path reads and mutates, validated back into typed canon values on read.
    """

    id: InvoiceId
    vendor_id: VendorId
    total: Decimal = Field(ge=0)
    due_date: date
    status: InvoiceStatus


class Store:
    """A SQLite-backed store. Each `connect()` is an independent transaction.

    Construct once (it creates the schema), then hand `connect()` to whoever owns a
    unit of work. Tests construct a `Store(tmp_path / "ap.db")` and open a *second*
    connection to read effects back — the visibility check a dict cannot offer.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        with self.connect() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def __repr__(self) -> str:
        return f"Store(path={self._path.name!r})"

    def connect(self) -> sqlite3.Connection:
        """Open a fresh connection — its own transaction, isolated from every other."""
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn


def seed_invoice(conn: sqlite3.Connection, invoice: StoredInvoice) -> None:
    """Insert an invoice in the caller's transaction. Does not commit."""
    conn.execute(
        "INSERT INTO invoices (id, vendor_id, total, due_date, status) VALUES (?, ?, ?, ?, ?)",
        (
            str(invoice.id),
            str(invoice.vendor_id),
            str(invoice.total),
            invoice.due_date.isoformat(),
            invoice.status.value,
        ),
    )


def read_invoice(conn: sqlite3.Connection, invoice_id: InvoiceId) -> StoredInvoice:
    """Read one invoice, or raise — a missing invoice is a contract violation here,
    not a queryable absence (the caller seeded it)."""
    row = conn.execute(
        "SELECT id, vendor_id, total, due_date, status FROM invoices WHERE id = ?",
        (str(invoice_id),),
    ).fetchone()
    if row is None:
        raise KeyError(f"no invoice {invoice_id!r} in store")
    return StoredInvoice.model_validate(dict(row))


def insert_payment(conn: sqlite3.Connection, payment: Payment) -> None:
    """Stage a payment row in the caller's transaction. Does not commit. The UNIQUE
    idempotency_key means a replay raises `sqlite3.IntegrityError` — the boundary
    rolls back, so the same key never pays twice."""
    conn.execute(
        "INSERT INTO payments (invoice_id, amount, idempotency_key, scheduled_for) VALUES (?, ?, ?, ?)",
        (
            str(payment.invoice_id),
            str(payment.amount),
            payment.idempotency_key,
            payment.scheduled_for.isoformat(),
        ),
    )


def set_status(
    conn: sqlite3.Connection, invoice_id: InvoiceId, status: InvoiceStatus
) -> None:
    """Mutate an invoice's status in the caller's transaction. Does not commit."""
    conn.execute(
        "UPDATE invoices SET status = ? WHERE id = ?",
        (status.value, str(invoice_id)),
    )


def read_payment(conn: sqlite3.Connection, invoice_id: InvoiceId) -> Payment | None:
    """Read the payment for an invoice, or None if none exists.

    Absence is a legitimate queried state here — "has this invoice been paid yet?" —
    not a contract failure, so this returns `Payment | None` rather than raising.
    """
    row = conn.execute(
        "SELECT invoice_id, amount, idempotency_key, scheduled_for FROM payments WHERE invoice_id = ?",
        (str(invoice_id),),
    ).fetchone()
    if row is None:
        return None
    return Payment.model_validate(dict(row))
