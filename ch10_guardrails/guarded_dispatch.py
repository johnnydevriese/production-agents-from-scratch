"""Wire the guards into the loop — a tripped guard is a ROUTING event, not a crash.

`schedule_payment` is MONEY_MOVEMENT (Chapter 3's `TOOL_RISK`), so the Layer-2 gate
blocks it unless a human set `confirmed`. A blocked money-movement call DEGRADES TO
A HUMAN via `request_approval` (EXTERNAL_COMMS) — the work isn't crashed and isn't
silently dropped. Critically, the vendor banking the human then verifies comes from
`get_vendor`, never from the (fenced) invoice text an attacker controls.
"""

from __future__ import annotations

from autopilot.models import ApprovalRequest, InvoiceId, Payment
from ch06_facade.facade import RailPaymentFacade

from .guardrails import GuardrailTripped, gate_tool_call


def settle_or_escalate(
    invoice_id: InvoiceId,
    *,
    facade: RailPaymentFacade,
    confirmed: bool,
    idempotency_key: str,
) -> Payment | ApprovalRequest:
    """The guarded money-movement step: pay iff a human confirmed, else escalate."""
    try:
        gate_tool_call("schedule_payment", confirmed=confirmed)
    except GuardrailTripped as tripped:
        return facade.request_approval(
            invoice_id, reason=f"auto-payment gated: {tripped}"
        )
    return facade.schedule_payment(invoice_id, idempotency_key=idempotency_key)
