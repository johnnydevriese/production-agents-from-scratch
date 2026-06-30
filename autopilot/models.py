"""Canonical domain models for the AP autopilot.

This is the *anchor*: every chapter in the book quotes these exact types and
names. Chapters add behavior; they do not redefine the domain. If a model needs
to change, change it here and the whole book stays consistent.

Money is `Decimal`, never `float`. IDs are `NewType` so an InvoiceId can't be
passed where a VendorId is expected (the type checker catches it).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import NewType

from pydantic import BaseModel, Field

InvoiceId = NewType("InvoiceId", str)
VendorId = NewType("VendorId", str)
PurchaseOrderId = NewType("PurchaseOrderId", str)


class InvoiceStatus(str, Enum):
    RECEIVED = "received"
    MATCHED = "matched"
    EXCEPTION = "exception"   # matching found a discrepancy a human must resolve
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PAID = "paid"


class LineItem(BaseModel):
    description: str
    quantity: int = Field(ge=0)
    unit_price: Decimal = Field(ge=0)
    amount: Decimal = Field(ge=0)


class Invoice(BaseModel):
    id: InvoiceId
    vendor_id: VendorId
    purchase_order_id: PurchaseOrderId | None = None
    invoice_date: date
    due_date: date
    currency: str = "USD"
    line_items: list[LineItem]
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    status: InvoiceStatus = InvoiceStatus.RECEIVED


class Vendor(BaseModel):
    id: VendorId
    name: str
    # Bank details are secrets — repr=False is log hygiene, not a boundary.
    bank_account: str = Field(repr=False)
    routing_number: str = Field(repr=False)


class MatchResult(BaseModel):
    invoice_id: InvoiceId
    matched: bool
    purchase_order_id: PurchaseOrderId | None = None
    discrepancies: list[str] = Field(default_factory=list)


class BudgetCheck(BaseModel):
    department: str
    amount: Decimal
    budget_remaining: Decimal
    within_budget: bool


class ApprovalRequest(BaseModel):
    invoice_id: InvoiceId
    reason: str
    approver: str | None = None


class Payment(BaseModel):
    invoice_id: InvoiceId
    amount: Decimal
    idempotency_key: str   # the same key never pays twice (Chapter 26)
    scheduled_for: date


class JournalEntry(BaseModel):
    invoice_id: InvoiceId
    debit_account: str
    credit_account: str
    amount: Decimal
