"""Authorization: who may invoke a tool, not just whether the tool is dangerous.

Chapter 10's `confirmed` flag asked *did a human assent?* — necessary, nowhere near
sufficient. It never asked *is **this** human **allowed**?* A confirmation from an
identity with no payment permission is theatre. This module adds the missing
question: a request-scoped `SecurityContext`, built at the edge from a verified
session and *never* from model output, plus a data-driven role→risk-tier table that
fails closed — the same shape as `TOOL_RISK`, grown a column.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from autopilot.tools import TOOL_RISK, RiskTier


class Role(str, Enum):
    VIEWER = "viewer"  # read-only: lookups, matching, budget checks
    PREPARER = "preparer"  # may request approval, draft payments
    APPROVER = "approver"  # may authorize money movement + irreversible writes


class SecurityContext(BaseModel):
    """Who is acting, and what they may do.

    Built from a verified session at the edge — NEVER from model output or
    conversation content. The principal is `repr=False` and omitted from the custom
    `__repr__`, so it can never land in a log line or span attribute.
    """

    principal_id: str = Field(repr=False)
    role: Role
    session_id: str

    def __repr__(self) -> str:
        return f"SecurityContext(role={self.role.value}, session={self.session_id})"


# Data-driven, like TOOL_RISK: which role may invoke which risk tier. Fails closed.
_ROLE_MAX_TIER: dict[Role, frozenset[RiskTier]] = {
    Role.VIEWER: frozenset({RiskTier.READ_ONLY}),
    Role.PREPARER: frozenset({RiskTier.READ_ONLY, RiskTier.EXTERNAL_COMMS}),
    Role.APPROVER: frozenset(RiskTier),  # every tier — the only role that may pay
}


class Unauthorized(Exception):
    """This identity may not invoke this tool. Distinct from GuardrailTripped."""


def authorize_tool_call(tool_name: str, *, ctx: SecurityContext) -> None:
    """Raise `Unauthorized` if this identity's role may not invoke this tool.

    No return value — it permits execution or refuses. `TOOL_RISK[tool_name]` raises
    `KeyError` on an unknown tool, so an invented tool is blocked, not allowed.
    """
    tier = TOOL_RISK[tool_name]  # KeyError on unknown tool = fail closed
    if tier not in _ROLE_MAX_TIER[ctx.role]:
        raise Unauthorized(
            f"role {ctx.role.value} may not invoke {tool_name} ({tier.value})"
        )
