"""Non-repudiation: the audit trail records who authorized what, on what evidence.

Authorization decides *whether* a privileged action runs; the audit trail records
*that it ran, who authorized it, and on what evidence* — permanently and tamper-
evidently. The trace (Chapter 18) shows what the agent did; the audit log shows who
was allowed to make it do that, and the two are not the same record.

Three properties separate this from "we have logs": it is append-only and
tamper-evident (a hash chain makes any later edit or deletion detectable), it records
the *authorization* (principal, role, confirmer) not just the action, and it is
written on the refusal too — a trail that logs only successes is blind to exactly the
attacks you most need to investigate. And, like every artifact that crosses a
boundary, it holds no secret.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from autopilot.models import InvoiceId
from autopilot.tools import RiskTier

from .security import Role

_GENESIS = "0" * 64


class Outcome(str, Enum):
    EXECUTED = "executed"
    UNAUTHORIZED = "unauthorized"  # blocked by authorization — written anyway
    GATED = "gated"  # blocked by the Ch 10 confirmation gate


class AuditRecord(BaseModel):
    """An append-only, non-repudiable record of one privileged action.

    Written for every non-`READ_ONLY` tool call, regardless of outcome. There is no
    `bank_account` and no `routing_number` field — the audit log is not an exfil
    channel either.
    """

    model_config = {"frozen": True}

    ts: datetime  # tz-aware UTC, always
    session_id: str
    principal_id: str = Field(repr=False)  # who — in the record, not the repr
    role: Role
    tool_name: str
    risk_tier: RiskTier
    invoice_id: InvoiceId | None = None
    confirmed_by: str | None = None  # the approver identity, if confirmation applied
    outcome: Outcome

    @model_validator(mode="after")
    def _ts_is_aware(self) -> AuditRecord:
        if self.ts.tzinfo is None:
            raise ValueError("audit timestamps must be timezone-aware (UTC)")
        return self


class ChainedEntry(BaseModel):
    """One link in the tamper-evident chain: a record bound to those before it."""

    model_config = {"frozen": True}

    seq: int
    record: AuditRecord
    prev_hash: str
    entry_hash: str


def _link_hash(prev_hash: str, record: AuditRecord) -> str:
    return hashlib.sha256(
        (prev_hash + record.model_dump_json()).encode("utf-8")
    ).hexdigest()


class HashChainedAuditLog:
    """An append-only audit log whose links are chained by hash.

    Editing or deleting any record after the fact breaks the chain — `verify`
    recomputes every link and returns False the moment one doesn't match.
    """

    def __init__(self) -> None:
        self.entries: list[ChainedEntry] = []

    def __repr__(self) -> str:
        ok = "intact" if self.verify() else "TAMPERED"
        return f"HashChainedAuditLog(entries={len(self.entries)}, chain={ok})"

    def append(self, record: AuditRecord) -> ChainedEntry:
        prev = self.entries[-1].entry_hash if self.entries else _GENESIS
        entry = ChainedEntry(
            seq=len(self.entries),
            record=record,
            prev_hash=prev,
            entry_hash=_link_hash(prev, record),
        )
        self.entries.append(entry)
        return entry

    def verify(self) -> bool:
        """Recompute the chain end-to-end; any edit, deletion, or reorder fails it."""
        prev = _GENESIS
        for i, entry in enumerate(self.entries):
            if entry.seq != i or entry.prev_hash != prev:
                return False
            if _link_hash(prev, entry.record) != entry.entry_hash:
                return False
            prev = entry.entry_hash
        return True
