"""Compose the filters into the triage pass that feeds the annotation queue.

`FILTERS` is a data-driven table (name → predicate over a `Trace`), not an
if/elif chain — adding a filter is one row. `triage` runs them on one finished
trace and enqueues anything that smells, with the reasons attached so the analyst
sees *why* it was flagged. `triage_batch` runs the firehose and returns the
flagged-ratio shape: a human can review sixty-one invoices, not a hundred thousand.

The queue is injected (`AnnotationQueue` Protocol) — a real run writes to the
backend's annotation queue (the Ch 18 feedback-score mechanism, by hand for the
hard cases); the tests pass an in-memory `ListQueue`.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Sequence
from typing import Protocol

from pydantic import BaseModel, Field

from .filters import (
    path_skipped_budget,
    smells_like_account_change,
    smells_like_overpay,
)
from .models import Trace

logger = logging.getLogger(__name__)


class AnnotationQueue(Protocol):
    """The one method triage needs from the queue backend."""

    def enqueue(self, *, trace_id: str, reasons: list[str]) -> None: ...


class ListQueue:
    """In-memory annotation queue for tests and the demo."""

    def __init__(self) -> None:
        self.items: list[tuple[str, list[str]]] = []

    def enqueue(self, *, trace_id: str, reasons: list[str]) -> None:
        self.items.append((trace_id, reasons))


def _new_bank_account(trace: Trace) -> bool:
    return smells_like_account_change(
        vendor=trace.vendor, known_accounts=trace.known_accounts
    )


def _overpay(trace: Trace) -> bool:
    if trace.payment is None:
        return False  # nothing was paid → no overpay to flag
    return smells_like_overpay(
        payment=trace.payment, match=trace.match, po_total=trace.po_total
    )


def _missing_budget_check(trace: Trace) -> bool:
    return path_skipped_budget(tools_called=trace.tools_called)


FILTERS: dict[str, Callable[[Trace], bool]] = {
    "new_bank_account": _new_bank_account,
    "overpay": _overpay,
    "missing_budget_check": _missing_budget_check,
}


def reasons_for(trace: Trace) -> list[str]:
    """Names of every filter that fires on this trace, in table order."""
    return [name for name, fires in FILTERS.items() if fires(trace)]


def triage(trace: Trace, *, queue: AnnotationQueue) -> list[str]:
    """Run cheap checks on one production trace; enqueue anything that smells."""
    hits = reasons_for(trace)
    if hits:
        queue.enqueue(trace_id=trace.id, reasons=hits)
        logger.info("flagged trace %s for review: %s", trace.id, hits)
    return hits


class TriageReport(BaseModel):
    """The flagged-ratio shape — what a week of traffic looks like after triage."""

    scanned: int
    flagged: int
    reason_counts: dict[str, int] = Field(default_factory=dict)


def triage_batch(traces: Sequence[Trace], *, queue: AnnotationQueue) -> TriageReport:
    """Triage a firehose; enqueue the smelly ones; report the distribution."""
    counts: Counter[str] = Counter()
    flagged = 0
    for trace in traces:
        hits = triage(trace, queue=queue)
        if hits:
            flagged += 1
            counts.update(hits)
    return TriageReport(
        scanned=len(traces), flagged=flagged, reason_counts=dict(counts)
    )
