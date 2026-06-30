"""The wiring seam: authorize → gate → dispatch → audit. The order is the policy.

The Chapter 10 dispatch site grows two lines, not a rewrite. Authorization runs
*first* (*may this identity?*), then the Chapter 10 confirmation gate (*did a human
assent?*), then the tool, then the audit write. Because authorization is first, an
unprivileged identity's 'confirm' is never even evaluated — the difference between
"a human said yes" and "the *right* human said yes". Every non-READ_ONLY call leaves
an audit record on every path: executed, unauthorized, or gated.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from pydantic import BaseModel

from autopilot.models import InvoiceId
from autopilot.tools import TOOL_RISK, RiskTier

from ch10_guardrails.guardrails import GuardrailTripped, gate_tool_call

from .audit import AuditRecord, HashChainedAuditLog, Outcome
from .security import SecurityContext, Unauthorized, authorize_tool_call


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def secure_dispatch(
    *,
    tool_name: str,
    ctx: SecurityContext,
    confirmed: bool,
    dispatch: Callable[[], BaseModel],
    audit: HashChainedAuditLog,
    invoice_id: InvoiceId | None = None,
    confirmed_by: str | None = None,
    now: Callable[[], datetime] = _utc_now,
) -> BaseModel:
    """Run one tool call through the full trust pipeline, auditing the outcome."""
    tier = TOOL_RISK[tool_name]  # KeyError on unknown = fail closed
    privileged = tier is not RiskTier.READ_ONLY

    def _audit(outcome: Outcome) -> None:
        if privileged:
            audit.append(
                AuditRecord(
                    ts=now(),
                    session_id=ctx.session_id,
                    principal_id=ctx.principal_id,
                    role=ctx.role,
                    tool_name=tool_name,
                    risk_tier=tier,
                    invoice_id=invoice_id,
                    confirmed_by=confirmed_by,
                    outcome=outcome,
                )
            )

    try:
        authorize_tool_call(tool_name, ctx=ctx)  # NEW: may this identity?
    except Unauthorized:
        _audit(Outcome.UNAUTHORIZED)  # written on the refusal, too
        raise
    try:
        gate_tool_call(tool_name, confirmed=confirmed)  # Ch 10: did a human assent?
    except GuardrailTripped:
        _audit(Outcome.GATED)
        raise

    result = dispatch()  # only if both allow it
    _audit(Outcome.EXECUTED)
    return result
