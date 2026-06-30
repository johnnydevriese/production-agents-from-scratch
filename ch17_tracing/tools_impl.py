"""The tools the traced loop exercises — the read path plus escalation.

Chapter 17 is about *observing* the loop, not adding tools, so these are the
Chapter 3 read-only set plus `request_approval` (the `external_comms` escalation
the chapter's worked trace ends on). The implementations are the Chapter 6 facade
logic as free functions — the raw-client loop dispatches by name, exactly as in
Chapter 2.

Each read raises `LookupError` on a miss; the traced loop turns that into a
failed-tool span (`tool.ok = false`) rather than a crash.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from pydantic import BaseModel

from autopilot.fixtures import DEPT_BUDGETS, INVOICES, VENDORS
from autopilot.models import (
    ApprovalRequest,
    BudgetCheck,
    Invoice,
    InvoiceId,
    MatchResult,
    Vendor,
    VendorId,
)


def lookup_invoice(invoice_id: str) -> Invoice:
    return INVOICES[InvoiceId(invoice_id)]


def get_vendor(vendor_id: str) -> Vendor:
    return VENDORS[VendorId(vendor_id)]


def match_to_po(invoice_id: str) -> MatchResult:
    invoice = INVOICES[InvoiceId(invoice_id)]
    return MatchResult(
        invoice_id=invoice.id,
        matched=invoice.purchase_order_id is not None,
        purchase_order_id=invoice.purchase_order_id,
    )


def check_budget(*, department: str, amount: Decimal) -> BudgetCheck:
    remaining = DEPT_BUDGETS[department] - Decimal(str(amount))
    return BudgetCheck(
        department=department,
        amount=Decimal(str(amount)),
        budget_remaining=remaining,
        within_budget=remaining >= 0,
    )


def request_approval(invoice_id: str, *, reason: str) -> ApprovalRequest:
    return ApprovalRequest(invoice_id=InvoiceId(invoice_id), reason=reason)


DISPATCH: dict[str, Callable[..., BaseModel]] = {
    "lookup_invoice": lookup_invoice,
    "get_vendor": get_vendor,
    "match_to_po": match_to_po,
    "check_budget": check_budget,
    "request_approval": request_approval,
}
