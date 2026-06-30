"""The decision record — output #2 of every approval, the part teams drop.

A `bool` turns every click into a shrug; an `ApprovalDecision` turns it into a
candidate label. Two fields do the downstream work: `trace_id` (provenance back to
the span tree of Chapter 17, without which a correction is an orphaned opinion) and
`latency_ms` (the rubber-stamp tell — a 900 ms "approval" across a forty-item queue
is a reflex, not a judgment).

The invariants are enforced at construction: a reject must say why, an edit must
carry its edits, an approval-as-is carries none, the timestamp is timezone-aware
(this system never stores a naive datetime), and every decision carries the digest
of the exact proposed action payload the approver saw.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from autopilot.models import InvoiceId


class DecisionKind(str, Enum):
    APPROVED = "approved"  # agent's proposal accepted as-is
    EDITED = "edited"  # approved, but the human changed >=1 field
    REJECTED = "rejected"  # bounced back; no money moves


class FieldEdit(BaseModel):
    """One human correction, captured as a typed before/after diff."""

    field: str  # e.g. "JournalEntry.debit_account"
    proposed: str  # what the agent wanted
    corrected: str  # what the human changed it to


class ApprovalDecision(BaseModel):
    """The decision record. Output #2 of every approval — the part teams drop."""

    invoice_id: InvoiceId
    kind: DecisionKind
    approver: str = Field(min_length=1)  # WHO decided (not just "a human")
    decided_at: datetime
    reason: str | None = None  # required on REJECTED; the "why"
    edits: list[FieldEdit] = Field(default_factory=list)
    proposed_action_digest: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)  # ← provenance back to the span (Ch 17)
    latency_ms: int = Field(ge=0)  # how long they looked (a rubber-stamp tell)

    @model_validator(mode="after")
    def _kind_matches_edits(self) -> ApprovalDecision:
        if self.decided_at.tzinfo is None:
            raise ValueError("decided_at must be timezone-aware")
        if self.kind is DecisionKind.REJECTED and not (self.reason or "").strip():
            raise ValueError("a REJECTED decision must record a reason")
        if self.kind is DecisionKind.EDITED and not self.edits:
            raise ValueError("an EDITED decision must carry at least one edit")
        if self.kind is DecisionKind.APPROVED and self.edits:
            raise ValueError("an APPROVED decision is as-is — it carries no edits")
        return self


def is_probable_rubber_stamp(
    decision: ApprovalDecision, *, threshold_ms: int = 2_000
) -> bool:
    """A near-instant *approve* is a reflex, not a judgment.

    Only un-edited approvals can rubber-stamp: a reject states a reason and an edit
    changes a field, so both show the human did work. Chapter 23 weights a
    fast-approved decision differently from a 40-second edit.
    """
    return decision.kind is DecisionKind.APPROVED and decision.latency_ms < threshold_ms
