"""The capture path: persist the decision record *before* you move money.

The approval is a durable signal (Chapter 26): the loop pauses at
`request_approval`, blocks, and resumes only when an `ApprovalDecision` arrives. The
capture is not a side effect we remember to log — it *is* the resume payload.

The ordering is load-bearing. If you move money first and write the record second, a
crash between the two loses the label *and* leaves you unable to prove who authorized
a payment — an audit-trail failure on a money-movement action. So `resolve_approval`
persists first, then acts. Both side effects are injected, so the discipline is
testable with zero I/O.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from autopilot.models import Payment

from .decision import ApprovalDecision, DecisionKind
from .edits import ProposedAction, apply_edits, proposal_digest


class ApprovalBindingError(Exception):
    """The approval was for a different proposed action payload."""


class ApprovalOutcome(BaseModel):
    """The result of resolving an approval. `payment is None` ⇔ rejected, no money moved."""

    decision: ApprovalDecision
    payment: Payment | None


def resolve_approval(
    *,
    decision: ApprovalDecision,
    proposal: ProposedAction,
    persist: Callable[[ApprovalDecision], None],
    schedule: Callable[[ProposedAction], Payment],
) -> ApprovalOutcome:
    """Persist the decision record, then act on it — never the reverse.

    On a reject, the record is still persisted (who said no, and why, is itself an
    audit fact) but `schedule` is never called. On an approve or edit, the human's
    typed corrections are applied to fresh, valid objects and only then does money
    move — exactly once, via the idempotency key the `Payment` already carries.
    """
    expected_digest = proposal_digest(proposal)
    if decision.proposed_action_digest != expected_digest:
        raise ApprovalBindingError("approval decision does not match proposed action")

    persist(decision)  # output #2 first — audit trail + resume payload
    if decision.kind is DecisionKind.REJECTED:
        return ApprovalOutcome(decision=decision, payment=None)
    final = apply_edits(proposal, decision.edits)
    return ApprovalOutcome(decision=decision, payment=schedule(final))
