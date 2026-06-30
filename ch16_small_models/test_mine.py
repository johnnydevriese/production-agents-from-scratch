"""The label is the human's final account, and the edits are the gold.

These pin: the mined label is the FINAL booked account (never the teacher's guess,
which would cap the student at the teacher's accuracy); accepted reviews aren't
corrections; `corrections` isolates the high-value edited 4%; and the teacher's
agreement rate is its grade. Pure, no spend.
"""

from __future__ import annotations

import pytest

from autopilot.models import InvoiceId

from .gl_coder import GLAccount
from .mine import (
    GLReview,
    corrections,
    mine_gl_corrections,
    teacher_agreement_rate,
)


def _review(
    invoice_id: str, teacher: GLAccount, final: GLAccount, *, trace_id: str = "tr"
) -> GLReview:
    return GLReview(
        invoice_id=InvoiceId(invoice_id),
        teacher_debit=teacher,
        final_debit=final,
        trace_id=trace_id,
    )


def test_the_label_is_the_final_account_not_the_teachers_guess() -> None:
    # The accountant changed SUPPLIES → SOFTWARE_SAAS: the label is what they booked.
    reviews = [_review("INV-1", GLAccount.SUPPLIES, GLAccount.SOFTWARE_SAAS)]
    [example] = mine_gl_corrections(reviews)
    assert example.debit_account is GLAccount.SOFTWARE_SAAS
    assert example.is_correction is True


def test_accepted_reviews_are_confirmations_not_corrections() -> None:
    reviews = [_review("INV-1", GLAccount.SUPPLIES, GLAccount.SUPPLIES)]
    [example] = mine_gl_corrections(reviews)
    assert example.debit_account is GLAccount.SUPPLIES
    assert example.is_correction is False


def test_corrections_isolate_the_high_value_edits() -> None:
    reviews = [
        _review(
            "INV-1", GLAccount.SUPPLIES, GLAccount.SUPPLIES, trace_id="a"
        ),  # accepted
        _review("INV-2", GLAccount.SUPPLIES, GLAccount.FREIGHT, trace_id="b"),  # edited
        _review(
            "INV-3", GLAccount.SOFTWARE_SAAS, GLAccount.SOFTWARE_SAAS, trace_id="c"
        ),
    ]
    examples = mine_gl_corrections(reviews)
    edited = corrections(examples)

    assert len(examples) == 3  # every review is a training pair
    assert [example.trace_id for example in edited] == ["b"]  # only the edit is gold


def test_teacher_agreement_rate_is_the_accept_fraction() -> None:
    accepted = [
        _review(f"a-{i}", GLAccount.SUPPLIES, GLAccount.SUPPLIES, trace_id=f"a-{i}")
        for i in range(96)
    ]
    edited = [
        _review(f"e-{i}", GLAccount.SUPPLIES, GLAccount.FREIGHT, trace_id=f"e-{i}")
        for i in range(4)
    ]
    assert teacher_agreement_rate(accepted + edited) == 0.96


def test_grading_the_teacher_over_zero_reviews_raises() -> None:
    with pytest.raises(ValueError, match="zero reviews"):
        teacher_agreement_rate([])
