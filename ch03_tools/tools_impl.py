"""The read-only tools, implemented against the frozen fixture store.

Chapter 3's job is risk *labeling* and error *reporting*, not the full backend.
The four read-only tools that need no external system are real here; the writes
(`schedule_payment`, `post_journal_entry`, …) arrive behind a typed facade in
Chapter 6 and a durable workflow in Chapter 26. Each read raises `LookupError`
(`KeyError`) on a miss — `dispatch.py` turns that into an observation.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from pydantic import BaseModel

from autopilot.fixtures import DEPT_BUDGETS, INVOICES, VENDORS
from autopilot.models import BudgetCheck, Invoice, InvoiceId, Vendor, VendorId


def lookup_invoice(invoice_id: str) -> Invoice:
    return INVOICES[InvoiceId(invoice_id)]


def get_vendor(vendor_id: str) -> Vendor:
    return VENDORS[VendorId(vendor_id)]


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
    "check_budget": check_budget,
}
