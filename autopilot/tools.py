"""The autopilot's tool surface — the bounded menu of typed actions.

This is the *contract* every chapter builds against. The implementations evolve
chapter by chapter (in Ch 2 they're hand-wired; in Ch 6 they sit behind a typed
facade; in Ch 26 the money-movement one runs inside a durable workflow). The
*signatures and risk tiers below do not change* — they're the canon.

The risk tier of each tool drives everything in the safety story: read-only tools
do not need payment-style confirmation but still need auth/redaction, while
money-movement tools require confirmation and an idempotency key (Ch 10, Ch 26,
Ch 29).
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Protocol

from .models import (
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


class RiskTier(str, Enum):
    """Ordered least → most dangerous. Introduced in Chapter 3."""

    READ_ONLY = "read_only"
    REVERSIBLE_WRITE = "reversible_write"
    IRREVERSIBLE_WRITE = "irreversible_write"
    MONEY_MOVEMENT = "money_movement"
    EXTERNAL_COMMS = "external_comms"


class AutopilotTools(Protocol):
    """The seven typed runtime actions the AP agent may take. Names are frozen.

    Chapter 9 adds extract_invoice(invoice_text) -> Invoice as a structured
    extraction capability, but it is not part of this runtime action table.
    """

    def lookup_invoice(self, invoice_id: InvoiceId) -> Invoice: ...
    def get_vendor(self, vendor_id: VendorId) -> Vendor: ...
    def match_to_po(self, invoice_id: InvoiceId) -> MatchResult: ...
    def check_budget(self, *, department: str, amount: Decimal) -> BudgetCheck: ...
    def request_approval(self, invoice_id: InvoiceId, *, reason: str) -> ApprovalRequest: ...
    def schedule_payment(self, invoice_id: InvoiceId, *, idempotency_key: str) -> Payment: ...
    def post_journal_entry(self, entry: JournalEntry) -> JournalEntry: ...
    # extract_invoice(invoice_text) -> Invoice is a Chapter 9 extraction capability.


# Data-driven, not an if/elif chain: tool name -> how dangerous it is.
TOOL_RISK: dict[str, RiskTier] = {
    "lookup_invoice": RiskTier.READ_ONLY,
    "get_vendor": RiskTier.READ_ONLY,
    "match_to_po": RiskTier.READ_ONLY,
    "check_budget": RiskTier.READ_ONLY,
    "request_approval": RiskTier.EXTERNAL_COMMS,
    "schedule_payment": RiskTier.MONEY_MOVEMENT,
    "post_journal_entry": RiskTier.IRREVERSIBLE_WRITE,
}
