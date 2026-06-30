"""What the approver must see: proposal, evidence, and the policy diff.

A context-free button rubber-stamps because it gives the human no basis for
judgment. This builds the three panels a competent approver needs — all of it
reconstructable from the trace (Chapter 17) — and computes the panel teams skip:
the *policy diff*, the data-driven deltas ("first payment to this vendor," "amount
3.2× the median," "PO quantity short") that turn a rubber-stamp back into a
judgment.

The vendor's bank details are *masked* on the way out — an approval surface that
leaks `bank_account` is the Chapter 29 control failing. The view simply has no field
that carries the raw number.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from autopilot.models import (
    BudgetCheck,
    Invoice,
    JournalEntry,
    MatchResult,
    Payment,
    Vendor,
)

_OUTLIER_FACTOR = Decimal("2.0")  # amount this far above the median is worth a look


class PolicyCode(str, Enum):
    FIRST_PAYMENT = "first_payment"
    PO_MISMATCH = "po_mismatch"
    AMOUNT_OUTLIER = "amount_outlier"
    OVER_BUDGET = "over_budget"


class PolicyFlag(BaseModel):
    """One deviation from the norm, with a human-readable why."""

    code: PolicyCode
    message: str


class ApprovalContext(BaseModel):
    """Everything the policy rules read — assembled from the trace's tool results."""

    invoice: Invoice
    vendor: Vendor
    match: MatchResult
    budget: BudgetCheck
    proposed_payment: Payment
    proposed_journal_entry: JournalEntry | None = None
    paid_before: bool  # have we ever paid this vendor? (caller looks it up)
    vendor_median: Decimal | None = None  # this vendor's median payment, if known


def _first_payment(ctx: ApprovalContext) -> PolicyFlag | None:
    if ctx.paid_before:
        return None
    return PolicyFlag(
        code=PolicyCode.FIRST_PAYMENT, message="first payment to this vendor"
    )


def _po_mismatch(ctx: ApprovalContext) -> PolicyFlag | None:
    if ctx.match.matched and not ctx.match.discrepancies:
        return None
    detail = "; ".join(ctx.match.discrepancies) or "no matching PO"
    return PolicyFlag(
        code=PolicyCode.PO_MISMATCH, message=f"PO did not match: {detail}"
    )


def _amount_outlier(ctx: ApprovalContext) -> PolicyFlag | None:
    median = ctx.vendor_median
    if median is None or median <= 0:
        return None
    ratio = ctx.proposed_payment.amount / median
    if ratio <= _OUTLIER_FACTOR:
        return None
    return PolicyFlag(
        code=PolicyCode.AMOUNT_OUTLIER,
        message=f"amount {ratio:.1f}× this vendor's median",
    )


def _over_budget(ctx: ApprovalContext) -> PolicyFlag | None:
    if ctx.budget.within_budget:
        return None
    return PolicyFlag(
        code=PolicyCode.OVER_BUDGET,
        message=f"over budget: {ctx.budget.budget_remaining} remaining",
    )


# Data-driven, in display order — adding a deviation check is one row, not a branch.
POLICY_RULES: tuple[Callable[[ApprovalContext], PolicyFlag | None], ...] = (
    _first_payment,
    _po_mismatch,
    _amount_outlier,
    _over_budget,
)


def policy_diff(ctx: ApprovalContext) -> list[PolicyFlag]:
    """Every deviation-from-norm flag that fires on this proposal, in display order."""
    return [flag for rule in POLICY_RULES if (flag := rule(ctx)) is not None]


def _mask_account(account: str) -> str:
    """Show only the last four digits — never the full number on the approval surface."""
    tail = account[-4:]
    return f"****{tail}"


class ApprovalView(BaseModel):
    """The three panels the approver judges — proposal, evidence, policy diff.

    There is deliberately no field carrying the vendor's full `bank_account`; the
    only account string here is masked.
    """

    invoice_id: str
    routed_reason: str  # why the loop stopped (the ApprovalRequest.reason)
    proposed_payment: Payment
    proposed_journal_entry: JournalEntry | None
    vendor_name: str
    vendor_account_masked: str
    match: MatchResult
    budget: BudgetCheck
    policy_flags: list[PolicyFlag] = Field(default_factory=list)


def build_approval_view(ctx: ApprovalContext, *, routed_reason: str) -> ApprovalView:
    """Assemble the approver's view from the trace evidence, masking bank details."""
    return ApprovalView(
        invoice_id=ctx.invoice.id,
        routed_reason=routed_reason,
        proposed_payment=ctx.proposed_payment,
        proposed_journal_entry=ctx.proposed_journal_entry,
        vendor_name=ctx.vendor.name,
        vendor_account_masked=_mask_account(ctx.vendor.bank_account),
        match=ctx.match,
        budget=ctx.budget,
        policy_flags=policy_diff(ctx),
    )
