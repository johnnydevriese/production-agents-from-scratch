"""Frozen sample data — the offline backend every checkpoint can read.

These are the records the autopilot "looks up." They let `ch02_loop`,
`ch06_facade`, and the rest run and be tested without a real ERP. The numbers
match the worked example used from Chapter 1 onward: invoice INV-1043 from Acme
for $2,988.09, against an Engineering budget of $4,000.00 (so a successful
budget check leaves $1,011.91).

A second invoice, DC-2207 from Downtown Office Cleaning, carries *no* purchase
order — recurring janitorial work nobody cuts a PO for. It's the PO-less
exception that drives Chapter 8 (*Prompting for reliability*): a too-narrow
trigger skips matching it, so it sails past the one tool that would flag it.

Bank details are obviously fake — they exist only to exercise the
secrets-handling story in Chapter 29 (kept out of `repr`/logs via the model).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from .models import (
    Invoice,
    InvoiceId,
    InvoiceStatus,
    LineItem,
    PurchaseOrderId,
    Vendor,
    VendorId,
)

VENDORS: dict[VendorId, Vendor] = {
    VendorId("V-ACME"): Vendor(
        id=VendorId("V-ACME"),
        name="Acme Industrial Supply Co.",
        bank_account="000123456789",
        routing_number="021000021",
    ),
    VendorId("V-DOC"): Vendor(
        id=VendorId("V-DOC"),
        name="Downtown Office Cleaning LLC",
        bank_account="000987654321",
        routing_number="011401533",
    ),
}

INVOICES: dict[InvoiceId, Invoice] = {
    InvoiceId("INV-1043"): Invoice(
        id=InvoiceId("INV-1043"),
        vendor_id=VendorId("V-ACME"),
        purchase_order_id=PurchaseOrderId("PO-7781"),
        invoice_date=date(2026, 5, 31),
        due_date=date(2026, 6, 30),
        line_items=[
            LineItem(
                description="Hex bolts, pneumatic actuators, and freight — May 2026",
                quantity=1,
                unit_price=Decimal("2760.00"),
                amount=Decimal("2760.00"),
            ),
        ],
        subtotal=Decimal("2760.00"),
        tax=Decimal("228.09"),
        total=Decimal("2988.09"),
        status=InvoiceStatus.RECEIVED,
    ),
    InvoiceId("DC-2207"): Invoice(
        id=InvoiceId("DC-2207"),
        vendor_id=VendorId("V-DOC"),
        purchase_order_id=None,  # recurring janitorial work — no PO is cut for it
        invoice_date=date(2026, 6, 1),
        due_date=date(2026, 7, 1),  # Net 30
        line_items=[
            LineItem(
                description="Janitorial services — June 2026",
                quantity=1,
                unit_price=Decimal("1840.00"),
                amount=Decimal("1840.00"),
            ),
        ],
        subtotal=Decimal("1840.00"),
        tax=Decimal("0.00"),
        total=Decimal("1840.00"),
        status=InvoiceStatus.RECEIVED,
    ),
}

# Department budgets the autopilot checks `amount` against (Chapter 2 onward).
DEPT_BUDGETS: dict[str, Decimal] = {
    "Engineering": Decimal("4000.00"),
    "Marketing": Decimal("1500.00"),
    "Operations": Decimal("9000.00"),
}
