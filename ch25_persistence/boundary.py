"""Effect purity: tools stage, the boundary commits. One transaction per turn.

The bug was a tool that committed (or failed to commit) inside its own body. The
discipline: a tool *mutates in the session and returns a typed value* — it never
owns the transaction. Exactly one place does, the boundary that runs the loop, and
it commits once on success or rolls back wholesale on any failure. That is what
makes "half-applied turn" — invoice `SCHEDULED` but no `Payment` row — unreachable.

`run_turn` takes the turn's work as a callable so the boundary is testable with no
model and no network: in production `work` is the agent loop; in the suite it is a
closure that calls the pure tools below. Either way, durability is decided here.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import TypeVar

from autopilot import InvoiceId, InvoiceStatus, Payment

from .store import Store, insert_payment, read_invoice, set_status

T = TypeVar("T")


def schedule_payment(
    conn: sqlite3.Connection,
    invoice_id: InvoiceId,
    *,
    idempotency_key: str,
) -> Payment:
    """Stage a payment: mutate this transaction, return the typed `Payment`.

    Pure with respect to durability — it adds the payment row and moves the invoice
    to `SCHEDULED`, but it does **not** commit. The boundary decides whether this
    becomes an effect. (The Chapter 6 facade pattern, now with a real transaction
    behind it.)
    """
    invoice = read_invoice(conn, invoice_id)
    payment = Payment(
        invoice_id=invoice_id,
        amount=invoice.total,
        idempotency_key=idempotency_key,
        scheduled_for=invoice.due_date,
    )
    insert_payment(conn, payment)  # INSERT — not yet durable
    set_status(
        conn, invoice_id, InvoiceStatus.SCHEDULED
    )  # UPDATE — a mutation, not a commit
    return payment


def run_turn(store: Store, work: Callable[[sqlite3.Connection], T]) -> T:
    """One turn = one transaction, owned here.

    Open a connection, run the turn's work against it, and commit *once* on success;
    on any exception roll the whole turn back and re-raise so the caller decides.
    The work never commits — that is the entire boundary discipline, and it is why a
    turn that fails midway leaves no partial state behind.
    """
    conn = store.connect()
    try:
        result = work(conn)
        conn.commit()  # effects become durable HERE, once, after the whole turn
        return result
    except Exception:
        conn.rollback()  # a failed turn leaves NO partial state
        raise  # never swallow; the caller decides what a failed turn means
    finally:
        conn.close()
