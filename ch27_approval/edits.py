"""The bounded, typed edit surface — the third verb the interface needs.

If the only verbs are *approve* and *reject*, an approver who spots a *fixable*
problem has no move except a blunt reject, so they approve the imperfect thing
instead. The cure is *edit* — but a free-form text box would throw away the very
property that makes the autopilot safe: its actions are typed.

So the approver edits the *same Pydantic fields the agent proposed*, validated the
same way. The editable surface is a small, deliberate whitelist (`EDITABLE_FIELDS`);
everything else — notably `Vendor.bank_account`, the Chapter 10 injection vector and
a Chapter 29 control — is *not* editable from this surface. An edit produces a new,
*valid* domain object: the invariants that protected the agent now protect the
human's correction.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from pydantic import BaseModel

from autopilot.models import Invoice, JournalEntry, Payment

from .decision import FieldEdit


class ApprovalError(Exception):
    """Base for everything that can go wrong resolving an approval."""


class UneditableFieldError(ApprovalError):
    """An edit targeted a field outside the approval surface's whitelist."""


class ProposedAction(BaseModel):
    """What the loop paused on: the action the agent wants a human to bless."""

    invoice: Invoice
    payment: Payment
    journal_entry: JournalEntry | None = None


def proposal_digest(proposal: ProposedAction) -> str:
    """Stable digest of the exact action payload shown to the approver."""
    payload = json.dumps(
        proposal.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode()).hexdigest()


# field path → the attribute on ProposedAction it lives under. The map *is* the
# whitelist: a path absent here cannot be edited. `bank_account` is deliberately
# absent — a human must never hand-edit bank details inside a payment flow.
_TARGETS: dict[str, str] = {
    "JournalEntry.debit_account": "journal_entry",
    "JournalEntry.credit_account": "journal_entry",
    "Payment.amount": "payment",
    "Invoice.vendor_id": "invoice",
}

EDITABLE_FIELDS: frozenset[str] = frozenset(_TARGETS)


def _revalidate(model: BaseModel, *, field: str, value: str) -> BaseModel:
    """Rebuild the model through validation so the edit can't dodge the invariants."""
    return type(model).model_validate({**model.model_dump(), field: value})


def apply_edits(proposal: ProposedAction, edits: Sequence[FieldEdit]) -> ProposedAction:
    """Apply a human's typed corrections, returning a new, valid `ProposedAction`.

    The original is never mutated. Each edit must name a whitelisted field on a
    present object; anything else raises `UneditableFieldError`. The corrected value
    flows back through Pydantic validation, so a bad amount or a malformed id is
    rejected exactly as it would be on the agent's own path.
    """
    updated: dict[str, BaseModel] = {}
    for edit in edits:
        target = _TARGETS.get(edit.field)
        if target is None:
            raise UneditableFieldError(
                f"{edit.field!r} is not an editable field on the approval surface"
            )
        current = updated.get(target) or getattr(proposal, target)
        if current is None:
            raise UneditableFieldError(
                f"cannot edit {edit.field!r}: no {target} was proposed"
            )
        field_name = edit.field.split(".", 1)[1]
        updated[target] = _revalidate(current, field=field_name, value=edit.corrected)

    return proposal.model_copy(update=updated)
