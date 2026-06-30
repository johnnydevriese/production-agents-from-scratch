"""The approver's view — proposal + evidence + the policy diff. Pure, no spend.

These pin the panel teams skip (the data-driven policy diff that ends rubber-stamping)
and the Chapter 29 control: the view masks the vendor's bank account, and the raw
number appears nowhere in its serialized form.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from autopilot import (
    BudgetCheck,
    InvoiceId,
    JournalEntry,
    MatchResult,
    Payment,
    PurchaseOrderId,
)
from autopilot.fixtures import INVOICES, VENDORS

from .view import (
    ApprovalContext,
    PolicyCode,
    build_approval_view,
    policy_diff,
)


def _ctx(**over: object) -> ApprovalContext:
    invoice = INVOICES[InvoiceId("INV-1043")]
    vendor = VENDORS[invoice.vendor_id]
    base: dict[str, object] = {
        "invoice": invoice,
        "vendor": vendor,
        "match": MatchResult(
            invoice_id=invoice.id,
            matched=True,
            purchase_order_id=PurchaseOrderId("PO-7781"),
        ),
        "budget": BudgetCheck(
            department="ops",
            amount=invoice.total,
            budget_remaining=Decimal("61000.00"),
            within_budget=True,
        ),
        "proposed_payment": Payment(
            invoice_id=invoice.id,
            amount=invoice.total,
            idempotency_key="k-1",
            scheduled_for=date(2026, 7, 15),
        ),
        "proposed_journal_entry": JournalEntry(
            invoice_id=invoice.id,
            debit_account="6010",
            credit_account="2000",
            amount=invoice.total,
        ),
        "paid_before": True,
        "vendor_median": invoice.total,
    }
    return ApprovalContext.model_validate({**base, **over})


def test_a_clean_proposal_has_no_policy_flags() -> None:
    assert policy_diff(_ctx()) == []


def test_first_payment_to_a_vendor_is_flagged() -> None:
    flags = policy_diff(_ctx(paid_before=False))
    assert [f.code for f in flags] == [PolicyCode.FIRST_PAYMENT]


def test_a_po_discrepancy_is_flagged() -> None:
    invoice = INVOICES[InvoiceId("INV-1043")]
    bad_match = MatchResult(
        invoice_id=invoice.id, matched=False, discrepancies=["qty short by 12 units"]
    )
    flags = policy_diff(_ctx(match=bad_match))
    assert any(f.code is PolicyCode.PO_MISMATCH for f in flags)
    assert any("12 units" in f.message for f in flags)


def test_an_amount_far_above_the_median_is_flagged_with_its_ratio() -> None:
    # total 2988.09 against a median of 900 → 3.3× → outlier.
    flags = policy_diff(_ctx(vendor_median=Decimal("900.00")))
    outlier = next(f for f in flags if f.code is PolicyCode.AMOUNT_OUTLIER)
    assert "3.3×" in outlier.message


def test_an_over_budget_proposal_is_flagged() -> None:
    invoice = INVOICES[InvoiceId("INV-1043")]
    tight = BudgetCheck(
        department="ops",
        amount=invoice.total,
        budget_remaining=Decimal("-100.00"),
        within_budget=False,
    )
    flags = policy_diff(_ctx(budget=tight))
    assert any(f.code is PolicyCode.OVER_BUDGET for f in flags)


def test_flags_come_back_in_display_order() -> None:
    invoice = INVOICES[InvoiceId("INV-1043")]
    bad_match = MatchResult(invoice_id=invoice.id, matched=False)
    flags = policy_diff(_ctx(paid_before=False, match=bad_match))
    # first_payment is listed before po_mismatch in POLICY_RULES
    assert [f.code for f in flags] == [PolicyCode.FIRST_PAYMENT, PolicyCode.PO_MISMATCH]


def test_the_view_masks_the_bank_account() -> None:
    invoice = INVOICES[InvoiceId("INV-1043")]
    vendor = VENDORS[invoice.vendor_id]
    view = build_approval_view(_ctx(), routed_reason="match_exception")

    assert view.vendor_account_masked == "****6789"
    # the raw account leaks nowhere in the serialized view (the Ch 29 control)
    assert vendor.bank_account not in view.model_dump_json()


def test_the_view_carries_the_deviation_panel() -> None:
    view = build_approval_view(_ctx(paid_before=False), routed_reason="match_exception")
    assert any(f.code is PolicyCode.FIRST_PAYMENT for f in view.policy_flags)
    assert view.routed_reason == "match_exception"
