"""The capture path — persist the record before money moves. Pure, side effects injected.

These pin the ordering the chapter calls load-bearing: persist first, then act. On a
reject, the record is still persisted but nothing is scheduled. And if scheduling
crashes, the decision record is already durable — the authorization stays auditable.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from autopilot import InvoiceId, JournalEntry, Payment
from autopilot.fixtures import INVOICES

from .capture import ApprovalBindingError, resolve_approval
from .decision import ApprovalDecision, DecisionKind, FieldEdit
from .edits import ProposedAction, proposal_digest

_NOW = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)


def _proposal() -> ProposedAction:
    invoice = INVOICES[InvoiceId("INV-1043")]
    return ProposedAction(
        invoice=invoice,
        payment=Payment(
            invoice_id=invoice.id,
            amount=invoice.total,
            idempotency_key="k-1",
            scheduled_for=date(2026, 6, 30),
        ),
        journal_entry=JournalEntry(
            invoice_id=invoice.id,
            debit_account="6010",
            credit_account="2000",
            amount=invoice.total,
        ),
    )


def _decision(*, kind: DecisionKind, **over: object) -> ApprovalDecision:
    base: dict[str, object] = {
        "invoice_id": InvoiceId("INV-1043"),
        "kind": kind,
        "approver": "a.clerk",
        "decided_at": _NOW,
        "proposed_action_digest": proposal_digest(_proposal()),
        "trace_id": "trace-9921",
        "latency_ms": 30_000,
    }
    return ApprovalDecision.model_validate({**base, **over})


class _Recorder:
    """Records the order of side effects and the proposal that reached scheduling."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.persisted: list[ApprovalDecision] = []
        self.scheduled: ProposedAction | None = None

    def persist(self, decision: ApprovalDecision) -> None:
        self.events.append("persist")
        self.persisted.append(decision)

    def schedule(self, proposal: ProposedAction) -> Payment:
        self.events.append("schedule")
        self.scheduled = proposal
        return proposal.payment


def test_approve_persists_before_it_schedules() -> None:
    rec = _Recorder()
    outcome = resolve_approval(
        decision=_decision(kind=DecisionKind.APPROVED),
        proposal=_proposal(),
        persist=rec.persist,
        schedule=rec.schedule,
    )
    assert rec.events == ["persist", "schedule"]  # the record is durable first
    assert outcome.payment is not None


def test_reject_persists_the_record_but_moves_no_money() -> None:
    rec = _Recorder()
    outcome = resolve_approval(
        decision=_decision(kind=DecisionKind.REJECTED, reason="qty short by 12"),
        proposal=_proposal(),
        persist=rec.persist,
        schedule=rec.schedule,
    )
    assert rec.events == ["persist"]  # who said no, and why, is itself an audit fact
    assert outcome.payment is None


def test_an_edit_reaches_scheduling_already_corrected() -> None:
    rec = _Recorder()
    edit = FieldEdit(field="Payment.amount", proposed="2988.09", corrected="2900.00")
    resolve_approval(
        decision=_decision(kind=DecisionKind.EDITED, edits=[edit]),
        proposal=_proposal(),
        persist=rec.persist,
        schedule=rec.schedule,
    )
    assert rec.scheduled is not None
    assert rec.scheduled.payment.amount == Decimal("2900.00")


def test_an_approval_for_a_different_payload_is_refused_before_persisting() -> None:
    rec = _Recorder()
    with pytest.raises(ApprovalBindingError):
        resolve_approval(
            decision=_decision(
                kind=DecisionKind.APPROVED,
                proposed_action_digest="not-the-payload-the-human-saw",
            ),
            proposal=_proposal(),
            persist=rec.persist,
            schedule=rec.schedule,
        )
    assert rec.events == []


def test_a_crash_in_scheduling_leaves_the_decision_durable() -> None:
    rec = _Recorder()

    def _explode(_: ProposedAction) -> Payment:
        rec.events.append("schedule")
        raise RuntimeError("payment rail timed out")

    with pytest.raises(RuntimeError):
        resolve_approval(
            decision=_decision(kind=DecisionKind.APPROVED),
            proposal=_proposal(),
            persist=rec.persist,
            schedule=_explode,
        )
    # persist ran before the crash → the authorization is still on the record
    assert rec.events == ["persist", "schedule"]
    assert len(rec.persisted) == 1
