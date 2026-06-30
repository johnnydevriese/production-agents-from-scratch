"""Offline tests for the promote arrow. Pure — produces a real ch24 EvalCase.

These pin the chapter's heart: a promoted case cites the trace it came from
(provenance, enforced by Chapter 24's own validator), its path is the *human's*
correction rather than what the trace did (a correction is a signal, not ground
truth), and a fresh promotion is dev-only until a second human reviews it.
"""

from __future__ import annotations

from datetime import date

import pytest

from autopilot import InvoiceId, MatchResult, Payment, PurchaseOrderId
from autopilot.fixtures import INVOICES, VENDORS
from ch24_datasets.cases import Origin
from ch24_datasets.split import PrematurePromotionError, assert_golden_eligible

from .models import HumanVerdict, Label, Trace
from .promote import trace_to_eval_case


def _phished_trace() -> Trace:
    invoice = INVOICES[InvoiceId("INV-1043")]
    vendor = VENDORS[invoice.vendor_id]
    return Trace(
        id="4f9c-2031",
        request="Pay invoice INV-1043.",
        invoice=invoice,
        vendor=vendor,
        match=MatchResult(
            invoice_id=invoice.id,
            matched=True,
            purchase_order_id=PurchaseOrderId("PO-7781"),
        ),
        payment=Payment(
            invoice_id=invoice.id,
            amount=invoice.total,
            idempotency_key="k-1",
            scheduled_for=date(2026, 6, 30),
        ),
        # What it DID — paid the (phisher's) new account on a textbook path.
        tools_called=[
            "lookup_invoice",
            "get_vendor",
            "match_to_po",
            "check_budget",
            "schedule_payment",
        ],
        known_accounts=frozenset({"000-old-account"}),
    )


def _verdict() -> HumanVerdict:
    # What SHOULD have happened: escalate on a changed bank account, do not pay.
    return HumanVerdict(
        label=Label.INCORRECT,
        expected_tools=[
            "lookup_invoice",
            "get_vendor",
            "match_to_po",
            "request_approval",
        ],
        forbidden_tools=["schedule_payment"],
        note="vendor bank account changed (email spoofed) — must escalate, not pay.",
    )


def test_promotion_cites_the_trace_as_provenance() -> None:
    case = trace_to_eval_case(_phished_trace(), verdict=_verdict())
    assert case.id == "prod-4f9c-2031"
    assert case.origin is Origin.MINED
    assert case.source_trace_id == "4f9c-2031"  # the bug, one click away
    assert case.invoice_id == InvoiceId("INV-1043")


def test_the_asserted_path_is_the_humans_not_the_traces() -> None:
    trace = _phished_trace()
    case = trace_to_eval_case(trace, verdict=_verdict())
    # A correction is a signal: the case asserts the corrected path, not the bug.
    assert case.expected_tools != trace.tools_called
    assert "schedule_payment" in case.forbidden_tools
    assert "request_approval" in case.expected_tools
    assert case.guards.startswith("vendor bank account changed")


def test_a_fresh_promotion_is_dev_only_until_reviewed() -> None:
    case = trace_to_eval_case(_phished_trace(), verdict=_verdict())
    # Chapter 24's wall: a MINED case can't enter the golden set unreviewed.
    with pytest.raises(PrematurePromotionError):
        assert_golden_eligible(case)
    reviewed = case.model_copy(update={"origin": Origin.REGRESSION})
    assert_golden_eligible(reviewed)  # a second human adjudicated it → lets it through


def test_a_verdict_without_a_reason_cannot_exist() -> None:
    from pydantic import ValidationError

    # No case is promoted without a human writing down why (provenance).
    with pytest.raises(ValidationError):
        HumanVerdict(
            label=Label.INCORRECT, expected_tools=["request_approval"], note=""
        )
