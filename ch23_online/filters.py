"""Heuristic + structural filters — pure functions over a finished trace.

A filter is one boolean and needs no LLM; the discipline is "cheap checks gate the
firehose." Each is individually testable; `triage.py` composes them into the
data-driven set that turns 100,000 traces into the ~40 a human reviews today.

The bank-detail failure had a *signal* in the trace the structural evals missed:
`get_vendor` returned a `bank_account` never seen for that vendor. Paying a
vendor's account is the normal path, so no path assertion flags it — but
`smells_like_account_change` does.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from autopilot import MatchResult, Payment, Vendor

_OVERPAY_FACTOR = Decimal("3.0")


def smells_like_account_change(
    *, vendor: Vendor, known_accounts: frozenset[str]
) -> bool:
    """True when we're about to pay a bank account we've never paid before."""
    return vendor.bank_account not in known_accounts  # the missing signal


def smells_like_overpay(
    *, payment: Payment, match: MatchResult, po_total: Decimal | None
) -> bool:
    """Payment materially exceeds what the PO match justifies."""
    if not match.matched or match.purchase_order_id is None or po_total is None:
        return True  # paying an unmatched invoice is always worth a look
    return payment.amount > _OVERPAY_FACTOR * po_total


def path_skipped_budget(*, tools_called: Sequence[str]) -> bool:
    """Structural monitor: money moved without a budget check before it."""
    if "schedule_payment" not in tools_called:
        return False
    paid_at = list(tools_called).index("schedule_payment")
    return "check_budget" not in tools_called[:paid_at]
