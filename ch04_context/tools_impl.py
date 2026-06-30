"""The read-only tools this chapter's conversation exercises.

Chapter 4 is about *owning the working memory*, not about new tools, so the
implementations are the Chapter 3 read-only set plus `match_to_po` — the tool
whose `MatchResult` (carrying `purchase_order_id="PO-7781"`) is the load-bearing
fact a later `schedule_payment` needs and that naive truncation would drop.

Each read raises `LookupError` on a miss; the loop turns that into an
observation rather than a crash (the Chapter 3 dispatch discipline).
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from pydantic import BaseModel

from autopilot.fixtures import DEPT_BUDGETS, INVOICES, VENDORS
from autopilot.models import (
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
    """Three-way match against the PO on file. The PO id here is the fact that
    must survive compaction so a later schedule_payment can justify itself.
    """
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


DISPATCH: dict[str, Callable[..., BaseModel]] = {
    "lookup_invoice": lookup_invoice,
    "get_vendor": get_vendor,
    "match_to_po": match_to_po,
    "check_budget": check_budget,
}
