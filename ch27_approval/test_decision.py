"""The decision record's invariants — enforced at construction, no model, no spend.

These pin the chapter's claims about *output #2*: a reject must say why, an edit must
carry its edits, an as-is approval carries none, the timestamp is timezone-aware, and
a near-instant approval is the rubber-stamp tell the chapter exists to surface.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from autopilot import InvoiceId

from .decision import (
    ApprovalDecision,
    DecisionKind,
    FieldEdit,
    is_probable_rubber_stamp,
)

_NOW = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)


def _decision(*, kind: DecisionKind, **over: object) -> ApprovalDecision:
    base: dict[str, object] = {
        "invoice_id": InvoiceId("INV-1043"),
        "kind": kind,
        "approver": "a.clerk",
        "decided_at": _NOW,
        "proposed_action_digest": "proposal-sha256",
        "trace_id": "trace-9921",
        "latency_ms": 30_000,
    }
    return ApprovalDecision.model_validate({**base, **over})


def test_a_reject_without_a_reason_cannot_exist() -> None:
    with pytest.raises(ValidationError):
        _decision(kind=DecisionKind.REJECTED)  # no reason → invalid


def test_a_reject_with_a_reason_is_valid() -> None:
    d = _decision(kind=DecisionKind.REJECTED, reason="PO quantity short by 12 units")
    assert d.kind is DecisionKind.REJECTED


def test_an_edit_must_carry_its_edits() -> None:
    with pytest.raises(ValidationError):
        _decision(kind=DecisionKind.EDITED)  # EDITED but edits=[] → invalid


def test_an_as_is_approval_carries_no_edits() -> None:
    edit = FieldEdit(field="Payment.amount", proposed="100", corrected="90")
    with pytest.raises(ValidationError):
        _decision(kind=DecisionKind.APPROVED, edits=[edit])


def test_a_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _decision(kind=DecisionKind.APPROVED, decided_at=datetime(2026, 6, 25, 12, 0))


def test_a_decision_must_bind_to_a_proposed_action_digest() -> None:
    with pytest.raises(ValidationError):
        _decision(kind=DecisionKind.APPROVED, proposed_action_digest="")


def test_a_fast_approval_is_a_probable_rubber_stamp() -> None:
    assert is_probable_rubber_stamp(
        _decision(kind=DecisionKind.APPROVED, latency_ms=900)
    )


def test_a_considered_approval_is_not_flagged() -> None:
    slow = _decision(kind=DecisionKind.APPROVED, latency_ms=40_000)
    assert not is_probable_rubber_stamp(slow)


def test_only_un_edited_approvals_can_rubber_stamp() -> None:
    # A reject states a reason; an edit changes a field — both show real work.
    fast_reject = _decision(kind=DecisionKind.REJECTED, reason="no", latency_ms=10)
    edit = FieldEdit(field="Payment.amount", proposed="100", corrected="90")
    fast_edit = _decision(kind=DecisionKind.EDITED, edits=[edit], latency_ms=10)
    assert not is_probable_rubber_stamp(fast_reject)
    assert not is_probable_rubber_stamp(fast_edit)
