"""The wiring seam — authorize → gate → dispatch → audit. Pure, side effects injected.

These pin the order-is-policy claim: a viewer's 'confirm' is never evaluated because
authorization fails *first* (the outcome is UNAUTHORIZED, not GATED, and the tool
never runs). A privileged call leaves an audit record on every path; a READ_ONLY call
leaves none.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from autopilot import InvoiceId, Payment
from autopilot.models import Vendor, VendorId

from ch10_guardrails.guardrails import GuardrailTripped

from .audit import HashChainedAuditLog, Outcome
from .secure_loop import secure_dispatch
from .security import Role, SecurityContext, Unauthorized

_NOW = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)


def _fixed_now() -> datetime:
    return _NOW


def _ctx(role: Role) -> SecurityContext:
    return SecurityContext(principal_id="user-42", role=role, session_id="sess-1")


class _Dispatch:
    """Records whether the tool actually ran, and returns a canned result."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> Payment:
        self.calls += 1
        return Payment(
            invoice_id=InvoiceId("INV-1043"),
            amount=Decimal("2988.09"),
            idempotency_key="k-1",
            scheduled_for=date(2026, 6, 30),
        )


def test_a_viewer_paying_is_unauthorized_before_the_gate_is_even_reached() -> None:
    audit = HashChainedAuditLog()
    run = _Dispatch()
    with pytest.raises(Unauthorized):
        secure_dispatch(
            tool_name="schedule_payment",
            ctx=_ctx(Role.VIEWER),
            confirmed=True,  # a confirm that never gets evaluated
            dispatch=run,
            audit=audit,
            invoice_id=InvoiceId("INV-1043"),
            now=_fixed_now,
        )
    assert run.calls == 0  # the tool never ran
    assert [e.record.outcome for e in audit.entries] == [Outcome.UNAUTHORIZED]


def test_an_approver_without_confirmation_is_gated() -> None:
    audit = HashChainedAuditLog()
    run = _Dispatch()
    with pytest.raises(GuardrailTripped):
        secure_dispatch(
            tool_name="schedule_payment",
            ctx=_ctx(Role.APPROVER),
            confirmed=False,
            dispatch=run,
            audit=audit,
            now=_fixed_now,
        )
    assert run.calls == 0
    assert [e.record.outcome for e in audit.entries] == [Outcome.GATED]


def test_an_authorized_confirmed_payment_executes_and_audits() -> None:
    audit = HashChainedAuditLog()
    run = _Dispatch()
    result = secure_dispatch(
        tool_name="schedule_payment",
        ctx=_ctx(Role.APPROVER),
        confirmed=True,
        dispatch=run,
        audit=audit,
        invoice_id=InvoiceId("INV-1043"),
        confirmed_by="approver-7",
        now=_fixed_now,
    )
    assert isinstance(result, Payment)
    assert run.calls == 1
    assert [e.record.outcome for e in audit.entries] == [Outcome.EXECUTED]
    assert audit.verify()


def test_a_read_only_call_runs_without_an_audit_record() -> None:
    audit = HashChainedAuditLog()

    def _read() -> Vendor:
        return Vendor(
            id=VendorId("V-ACME"),
            name="Acme",
            bank_account="000123456789",
            routing_number="021000021",
        )

    result = secure_dispatch(
        tool_name="get_vendor",
        ctx=_ctx(Role.VIEWER),
        confirmed=False,
        dispatch=_read,
        audit=audit,
        now=_fixed_now,
    )
    assert isinstance(result, Vendor)
    assert audit.entries == []  # READ_ONLY is not a privileged action
