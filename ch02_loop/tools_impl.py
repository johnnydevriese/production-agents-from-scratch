"""Dispatch: turn a tool *name* the model emitted into a real function call.

The model can only name a tool; running it is our job. Dispatch is a dict, not an
if/elif chain. Both tools are read-only and return the canonical Pydantic models
from `autopilot/models.py`, read out of the frozen fixture store.

`lookup_invoice` raises `KeyError` on an unknown ID — Chapter 3 turns that into an
observation the model can see and recover from. Here it just propagates.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from pydantic import BaseModel

from autopilot.fixtures import DEPT_BUDGETS, INVOICES
from autopilot.models import BudgetCheck, Invoice, InvoiceId


def lookup_invoice(invoice_id: str) -> Invoice:
    return INVOICES[InvoiceId(invoice_id)]


def check_budget(*, department: str, amount: Decimal) -> BudgetCheck:
    remaining = DEPT_BUDGETS[department] - Decimal(str(amount))
    return BudgetCheck(
        department=department,
        amount=Decimal(str(amount)),
        budget_remaining=remaining,
        within_budget=remaining >= 0,
    )


# Dispatch table: tool name -> callable. No if/elif.
DISPATCH: dict[str, Callable[..., BaseModel]] = {
    "lookup_invoice": lookup_invoice,
    "check_budget": check_budget,
}
