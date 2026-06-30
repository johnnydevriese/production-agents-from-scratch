"""The audit trail — append-only, hash-chained, holds no secret. Pure, no spend.

These pin the three properties that separate an audit trail from "we have logs": it
is tamper-evident (editing any record after the fact breaks the chain), it carries no
bank details (it is not an exfil channel either), and its timestamps are tz-aware.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from autopilot import InvoiceId
from autopilot.tools import RiskTier

from .audit import AuditRecord, HashChainedAuditLog, Outcome
from .security import Role

_NOW = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)


def _record(*, outcome: Outcome = Outcome.EXECUTED, **over: object) -> AuditRecord:
    base: dict[str, object] = {
        "ts": _NOW,
        "session_id": "sess-1",
        "principal_id": "user-42",
        "role": Role.APPROVER,
        "tool_name": "schedule_payment",
        "risk_tier": RiskTier.MONEY_MOVEMENT,
        "invoice_id": InvoiceId("INV-1043"),
        "outcome": outcome,
    }
    return AuditRecord.model_validate({**base, **over})


def test_a_fresh_chain_verifies() -> None:
    log = HashChainedAuditLog()
    log.append(_record())
    log.append(_record(outcome=Outcome.UNAUTHORIZED, role=Role.VIEWER))
    assert log.verify()


def test_each_link_points_at_the_one_before_it() -> None:
    log = HashChainedAuditLog()
    first = log.append(_record())
    second = log.append(_record())
    assert second.prev_hash == first.entry_hash


def test_editing_a_record_after_the_fact_is_detectable() -> None:
    log = HashChainedAuditLog()
    log.append(_record(outcome=Outcome.UNAUTHORIZED))
    log.append(_record())
    # An insider rewrites the blocked attempt to look like a clean execution.
    tampered = log.entries[0].model_copy(
        update={
            "record": log.entries[0].record.model_copy(
                update={"outcome": Outcome.EXECUTED}
            )
        }
    )
    log.entries[0] = tampered
    assert not log.verify()  # the stale hash gives it away


def test_a_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _record(ts=datetime(2026, 6, 25, 12, 0))


def test_the_audit_record_holds_no_bank_details() -> None:
    assert "bank_account" not in AuditRecord.model_fields
    assert "routing_number" not in AuditRecord.model_fields


def test_a_refusal_is_recordable() -> None:
    # The blocked viewer escalation produces a record, not silence.
    rec = _record(outcome=Outcome.UNAUTHORIZED, role=Role.VIEWER)
    assert rec.outcome is Outcome.UNAUTHORIZED
