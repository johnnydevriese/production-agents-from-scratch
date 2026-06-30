"""Offline tests for the heuristic + structural filters. Pure — no LLM, no spend.

These pin the chapter's claims: the bank-detail signal a structural eval can't see
(`smells_like_account_change`), an overpay relative to the matched PO, and the
order-aware structural monitor that catches money moving before any budget check.
"""

from __future__ import annotations

from decimal import Decimal

from autopilot import InvoiceId, MatchResult, Payment, PurchaseOrderId, Vendor, VendorId

from .filters import (
    path_skipped_budget,
    smells_like_account_change,
    smells_like_overpay,
)


def _vendor(account: str) -> Vendor:
    return Vendor(
        id=VendorId("V-ACME"),
        name="Acme Industrial Supply Co.",
        bank_account=account,
        routing_number="021000021",
    )


def _payment(amount: str) -> Payment:
    from datetime import date

    return Payment(
        invoice_id=InvoiceId("INV-1043"),
        amount=Decimal(amount),
        idempotency_key="k-1",
        scheduled_for=date(2026, 6, 30),
    )


def _matched(*, matched: bool) -> MatchResult:
    return MatchResult(
        invoice_id=InvoiceId("INV-1043"),
        matched=matched,
        purchase_order_id=PurchaseOrderId("PO-7781") if matched else None,
    )


# --- the missing signal: a bank account never paid before -------------------------


def test_a_never_seen_account_is_flagged() -> None:
    # The phished-vendor case: the master record now holds a new account.
    vendor = _vendor("000999999999")
    known = frozenset({"000123456789"})  # the account we always paid
    assert smells_like_account_change(vendor=vendor, known_accounts=known)


def test_a_known_account_is_not_flagged() -> None:
    vendor = _vendor("000123456789")
    known = frozenset({"000123456789", "000111111111"})
    assert not smells_like_account_change(vendor=vendor, known_accounts=known)


# --- overpay relative to the matched PO -------------------------------------------


def test_overpay_flags_a_payment_far_above_the_po_total() -> None:
    assert smells_like_overpay(
        payment=_payment("3001.00"),
        match=_matched(matched=True),
        po_total=Decimal("1000.00"),
    )


def test_overpay_passes_a_payment_in_line_with_the_po() -> None:
    assert not smells_like_overpay(
        payment=_payment("2988.09"),
        match=_matched(matched=True),
        po_total=Decimal("2988.09"),
    )


def test_overpay_always_flags_an_unmatched_invoice() -> None:
    # No clean PO to justify the amount → always worth a human look.
    assert smells_like_overpay(
        payment=_payment("10.00"), match=_matched(matched=False), po_total=None
    )


# --- the structural monitor: money before a budget check --------------------------


def test_payment_without_a_preceding_budget_check_is_flagged() -> None:
    assert path_skipped_budget(
        tools_called=["lookup_invoice", "match_to_po", "schedule_payment"]
    )


def test_payment_after_a_budget_check_is_clean() -> None:
    assert not path_skipped_budget(
        tools_called=[
            "lookup_invoice",
            "match_to_po",
            "check_budget",
            "schedule_payment",
        ]
    )


def test_a_budget_check_after_the_payment_does_not_count() -> None:
    # Order matters: the check has to come *before* the money moves.
    assert path_skipped_budget(
        tools_called=["lookup_invoice", "schedule_payment", "check_budget"]
    )


def test_a_turn_that_never_paid_is_not_flagged() -> None:
    assert not path_skipped_budget(tools_called=["lookup_invoice", "match_to_po"])
