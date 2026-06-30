"""The bounded, typed edit surface — pure, no model, no spend.

These pin the chapter's two safety properties: the whitelist is the control (a field
absent from it — above all `bank_account` — can't be edited), and an edit produces a
new *valid* object (so a malformed correction is rejected exactly as the agent's own
path would be), while the original proposal is never mutated.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from autopilot import InvoiceId
from autopilot.fixtures import INVOICES

from .decision import FieldEdit
from .edits import (
    EDITABLE_FIELDS,
    ProposedAction,
    UneditableFieldError,
    apply_edits,
    proposal_digest,
)


def _proposal() -> ProposedAction:
    from autopilot.models import JournalEntry, Payment

    invoice = INVOICES[InvoiceId("INV-1043")]
    return ProposedAction(
        invoice=invoice,
        payment=Payment(
            invoice_id=invoice.id,
            amount=invoice.total,
            idempotency_key="k-1",
            scheduled_for=date(2026, 6, 30),
        ),
        journal_entry=JournalEntry(
            invoice_id=invoice.id,
            debit_account="6010",
            credit_account="2000",
            amount=invoice.total,
        ),
    )


def test_the_whitelist_is_exactly_the_four_fields() -> None:
    assert EDITABLE_FIELDS == {
        "JournalEntry.debit_account",
        "JournalEntry.credit_account",
        "Payment.amount",
        "Invoice.vendor_id",
    }
    assert "Vendor.bank_account" not in EDITABLE_FIELDS  # the control, restated


def test_a_gl_code_edit_produces_a_new_valid_object() -> None:
    proposal = _proposal()
    edit = FieldEdit(
        field="JournalEntry.debit_account", proposed="6010", corrected="6810"
    )

    corrected = apply_edits(proposal, [edit])

    assert corrected.journal_entry is not None
    assert corrected.journal_entry.debit_account == "6810"
    # the original is untouched — apply_edits returns a new object
    assert proposal.journal_entry is not None
    assert proposal.journal_entry.debit_account == "6010"


def test_an_amount_edit_coerces_through_validation() -> None:
    corrected = apply_edits(
        _proposal(),
        [FieldEdit(field="Payment.amount", proposed="2988.09", corrected="2900.00")],
    )
    assert corrected.payment.amount == Decimal("2900.00")


def test_editing_bank_details_is_refused() -> None:
    # The phishing vector: a human must never hand-edit bank details in a payment flow.
    with pytest.raises(UneditableFieldError):
        apply_edits(
            _proposal(),
            [
                FieldEdit(
                    field="Vendor.bank_account",
                    proposed="000123456789",
                    corrected="000999999999",
                )
            ],
        )


def test_editing_an_off_menu_field_is_refused() -> None:
    with pytest.raises(UneditableFieldError):
        apply_edits(
            _proposal(),
            [
                FieldEdit(
                    field="Payment.idempotency_key", proposed="k-1", corrected="k-2"
                )
            ],
        )


def test_editing_an_absent_object_is_refused() -> None:
    no_je = _proposal().model_copy(update={"journal_entry": None})
    with pytest.raises(UneditableFieldError):
        apply_edits(
            no_je,
            [
                FieldEdit(
                    field="JournalEntry.debit_account",
                    proposed="6010",
                    corrected="6810",
                )
            ],
        )


def test_a_malformed_correction_is_rejected_like_the_agents_path() -> None:
    with pytest.raises(ValidationError):
        apply_edits(
            _proposal(),
            [
                FieldEdit(
                    field="Payment.amount", proposed="2988.09", corrected="not-a-number"
                )
            ],
        )


def test_proposal_digest_changes_when_the_payload_changes() -> None:
    proposal = _proposal()
    corrected = apply_edits(
        proposal,
        [FieldEdit(field="Payment.amount", proposed="2988.09", corrected="2900.00")],
    )
    assert proposal_digest(proposal) != proposal_digest(corrected)
