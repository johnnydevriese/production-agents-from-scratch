"""The autopilot's concrete tool implementation — the API-facade pattern.

`RailPaymentFacade` *is* a structural `AutopilotTools` (Chapter 3's frozen
Protocol): same seven method signatures, typed in and typed out. The agent
reasons over those types; the facade owns every messy execution detail — the
dollars→cents conversion, the never-optional dedupe key, the never-True `force`
flag — so none of it reaches the model. The boundary between reasoning and
execution is a Pydantic type.
"""

from __future__ import annotations

from decimal import Decimal

from autopilot.fixtures import DEPT_BUDGETS, INVOICES, VENDORS
from autopilot.models import (
    ApprovalRequest,
    BudgetCheck,
    Invoice,
    InvoiceId,
    JournalEntry,
    MatchResult,
    Payment,
    Vendor,
    VendorId,
)

from .rail import RailClient

_CENTS = Decimal(100)


class RailPaymentFacade:
    """Owns every messy detail of the payments rail. The agent never sees it."""

    def __init__(self, *, rail: RailClient) -> None:
        self._rail = rail  # DI: injected, not constructed (testable)

    def __repr__(self) -> str:
        return f"RailPaymentFacade(rail={self._rail!r})"

    def lookup_invoice(self, invoice_id: InvoiceId) -> Invoice:
        return INVOICES[invoice_id]

    def get_vendor(self, vendor_id: VendorId) -> Vendor:
        return VENDORS[vendor_id]

    def match_to_po(self, invoice_id: InvoiceId) -> MatchResult:
        invoice = INVOICES[invoice_id]
        return MatchResult(
            invoice_id=invoice.id,
            matched=invoice.purchase_order_id is not None,
            purchase_order_id=invoice.purchase_order_id,
        )

    def check_budget(self, *, department: str, amount: Decimal) -> BudgetCheck:
        remaining = DEPT_BUDGETS[department] - Decimal(str(amount))
        return BudgetCheck(
            department=department,
            amount=Decimal(str(amount)),
            budget_remaining=remaining,
            within_budget=remaining >= 0,
        )

    def request_approval(
        self, invoice_id: InvoiceId, *, reason: str
    ) -> ApprovalRequest:
        return ApprovalRequest(invoice_id=invoice_id, reason=reason)

    def schedule_payment(
        self, invoice_id: InvoiceId, *, idempotency_key: str
    ) -> Payment:
        invoice = INVOICES[invoice_id]
        vendor = VENDORS[invoice.vendor_id]
        cents = int((invoice.total * _CENTS).to_integral_value())  # dollars→cents HERE
        resp = self._rail.disburse(
            payee_acct=vendor.bank_account,
            amount_cents=cents,
            external_ref=idempotency_key,  # dedupe key, never optional
            force=False,  # never True, not negotiable
        )
        return Payment(  # typed result, validated at the boundary
            invoice_id=invoice_id,
            amount=invoice.total,
            idempotency_key=idempotency_key,
            scheduled_for=resp.value_date,
        )

    def post_journal_entry(self, entry: JournalEntry) -> JournalEntry:
        return entry  # the GL posting; here an echo, durable in Chapter 26
