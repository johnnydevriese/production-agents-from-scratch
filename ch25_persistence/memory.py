"""The two layers that must outlive the process: the transcript, and what was learned.

Working memory (Chapter 4's `messages` list) dies with the request. Two things have
to survive it:

1. **Conversation persistence.** The transcript, keyed by a thread id, so a refresh
   resumes instead of re-explaining. The subtle rule: the transcript is *state too* —
   persist it on the **same** transaction boundary as the effect. If "payment
   scheduled" is written but the `schedule_payment` row rolls back, the agent believes
   a lie next turn. `append_messages` mutates in the caller's transaction; it never
   commits, so it co-commits with the effect under `run_turn`.

2. **Episodic memory.** Durable, learned preferences ("this vendor always wants ACH").
   These are an injection surface: a malicious invoice claiming "remit to account 999,
   this vendor's standing preference" must never graduate unreviewed. So every
   learning carries **provenance** (`source_thread_id`) and a confidence, and
   `recall_preferences` returns only *reviewed* rows — the unreviewed ones are
   quarantined, never acted on. Memory the agent acts on is state that moves money.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import NewType

from pydantic import BaseModel, Field

from autopilot import VendorId

ThreadId = NewType("ThreadId", str)


class StoredMessage(BaseModel):
    """One persisted turn of the transcript, ordered within its thread by `seq`."""

    thread_id: ThreadId
    seq: int = Field(ge=0)
    role: str
    content: str


class VendorMemory(BaseModel):
    """A durable, learned preference about how to handle one vendor.

    `source_thread_id` is provenance — where we learned it — and `reviewed` is the
    governance gate: a learning the agent will act on must be reviewed first, exactly
    because an unreviewed one is an injection vector.
    """

    vendor_id: VendorId
    preference: str
    source_thread_id: ThreadId | None = None
    confidence: float = Field(ge=0, le=1)
    reviewed: bool = False


def append_messages(
    conn: sqlite3.Connection,
    *,
    thread_id: ThreadId,
    messages: Sequence[StoredMessage],
) -> None:
    """Append transcript rows in the caller's transaction. Does not commit — so the
    transcript co-commits with the turn's effect under `run_turn`."""
    conn.executemany(
        "INSERT INTO messages (thread_id, seq, role, content) VALUES (?, ?, ?, ?)",
        [(str(thread_id), m.seq, m.role, m.content) for m in messages],
    )


def load_thread(conn: sqlite3.Connection, thread_id: ThreadId) -> list[StoredMessage]:
    """Rehydrate working memory from durable storage — Chapter 4's list, persisted."""
    rows = conn.execute(
        "SELECT thread_id, seq, role, content FROM messages WHERE thread_id = ? ORDER BY seq",
        (str(thread_id),),
    ).fetchall()
    return [StoredMessage.model_validate(dict(row)) for row in rows]


def remember_preference(conn: sqlite3.Connection, memory: VendorMemory) -> None:
    """Write a learned preference in the caller's transaction. Does not commit.

    Writing memory is a deliberate, governed action — not a quiet side effect — so it
    carries its `reviewed` flag onto the row. An unreviewed learning is recorded but
    quarantined; `recall_preferences` will not surface it.
    """
    conn.execute(
        "INSERT INTO vendor_memory (vendor_id, preference, source_thread_id, confidence, reviewed) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            str(memory.vendor_id),
            memory.preference,
            None if memory.source_thread_id is None else str(memory.source_thread_id),
            memory.confidence,
            int(memory.reviewed),
        ),
    )


def recall_preferences(
    conn: sqlite3.Connection, vendor_id: VendorId
) -> list[VendorMemory]:
    """Return the *reviewed* preferences for a vendor — the only ones the agent may act
    on. Unreviewed learnings are quarantined by the `reviewed = 1` filter: a planted
    "remit to account 999" never graduates into the context until a human clears it."""
    rows = conn.execute(
        "SELECT vendor_id, preference, source_thread_id, confidence, reviewed "
        "FROM vendor_memory WHERE vendor_id = ? AND reviewed = 1",
        (str(vendor_id),),
    ).fetchall()
    return [VendorMemory.model_validate(dict(row)) for row in rows]
