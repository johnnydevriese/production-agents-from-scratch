"""Mine GL-coding training pairs from the teacher's proposals and the human edits.

The teacher's outputs alone would cap the student at the teacher's 96% — the
student would faithfully learn the same 4% of mistakes. The point of doing this in
a production AP system is the second, higher-quality signal the teacher never saw:
every time an accountant changes a GL code on the approval screen (Ch 27), they
hand us a graded correction. The label is the *final, human-reviewed* account, not
the teacher's guess.

A correction is a strong label, not a certified oracle (Ch 23) — accountants
sometimes edit for one-off reasons that shouldn't generalize. Pure functions over
reviewed decisions; no model, no spend.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from enum import Enum

from pydantic import BaseModel

from autopilot.models import InvoiceId

from .gl_coder import GLAccount


class GLReviewOutcome(str, Enum):
    ACCEPTED = "accepted"  # the accountant accepted the teacher's proposal
    EDITED = "edited"  # the accountant changed it — the high-value 4%


class GLReview(BaseModel):
    """One GL-coding decision reviewed on the approval screen (Ch 27)."""

    invoice_id: InvoiceId
    teacher_debit: GLAccount  # what the frontier model proposed
    final_debit: GLAccount  # what was booked after human review
    trace_id: str

    @property
    def outcome(self) -> GLReviewOutcome:
        """Derived, never stored: an edit is any review where the booked account
        differs from the teacher's proposal — one source of truth."""
        if self.final_debit == self.teacher_debit:
            return GLReviewOutcome.ACCEPTED
        return GLReviewOutcome.EDITED


class GLExample(BaseModel):
    """A mined training pair: an invoice and its correct, human-reviewed account."""

    invoice_id: InvoiceId
    debit_account: GLAccount  # gold = the FINAL booked account, not the teacher's guess
    is_correction: bool  # the human changed the teacher's proposal (the gold 4%)
    trace_id: str


def mine_gl_corrections(reviews: Iterable[GLReview]) -> list[GLExample]:
    """Every reviewed decision is a training pair; the label is the *final* account.

    Accepted reviews confirm the teacher; edited ones are pure gold — exactly the
    cases the teacher got wrong, with the right answer attached.
    """
    return [
        GLExample(
            invoice_id=review.invoice_id,
            debit_account=review.final_debit,
            is_correction=review.outcome is GLReviewOutcome.EDITED,
            trace_id=review.trace_id,
        )
        for review in reviews
    ]


def corrections(examples: Sequence[GLExample]) -> list[GLExample]:
    """The edited subset — the highest-value training data (the teacher's blind spot)."""
    return [example for example in examples if example.is_correction]


def teacher_agreement_rate(reviews: Sequence[GLReview]) -> float:
    """Fraction of reviews the accountant accepted unchanged — the teacher's grade."""
    if not reviews:
        raise ValueError("cannot grade the teacher over zero reviews")
    accepted = sum(review.outcome is GLReviewOutcome.ACCEPTED for review in reviews)
    return accepted / len(reviews)
