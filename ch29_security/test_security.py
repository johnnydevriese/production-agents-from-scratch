"""Authorization — the role→risk-tier table, checked before the gate. Pure, no spend.

These pin the cold open's second attack: confirmation is not authorization. A viewer
may read but not pay; a preparer may request approval but not move money; only an
approver may pay. The identity never appears in the context's repr, and an unknown
tool fails closed.
"""

from __future__ import annotations

import pytest

from .security import Role, SecurityContext, Unauthorized, authorize_tool_call


def _ctx(role: Role) -> SecurityContext:
    return SecurityContext(
        principal_id="user-42-secret", role=role, session_id="sess-1"
    )


def test_the_principal_never_appears_in_the_repr() -> None:
    ctx = _ctx(Role.VIEWER)
    assert "user-42-secret" not in repr(ctx)  # never in a log line
    assert "viewer" in repr(ctx)


def test_a_viewer_may_read_but_not_pay() -> None:
    authorize_tool_call("lookup_invoice", ctx=_ctx(Role.VIEWER))  # READ_ONLY: fine
    with pytest.raises(Unauthorized):
        authorize_tool_call("schedule_payment", ctx=_ctx(Role.VIEWER))  # MONEY_MOVEMENT


def test_a_viewer_may_not_even_request_approval() -> None:
    with pytest.raises(Unauthorized):
        authorize_tool_call("request_approval", ctx=_ctx(Role.VIEWER))  # EXTERNAL_COMMS


def test_a_preparer_may_request_approval_but_not_move_money() -> None:
    authorize_tool_call(
        "request_approval", ctx=_ctx(Role.PREPARER)
    )  # EXTERNAL_COMMS: fine
    with pytest.raises(Unauthorized):
        authorize_tool_call("schedule_payment", ctx=_ctx(Role.PREPARER))


def test_only_an_approver_may_pay_and_post() -> None:
    ctx = _ctx(Role.APPROVER)
    authorize_tool_call("schedule_payment", ctx=ctx)  # MONEY_MOVEMENT
    authorize_tool_call("post_journal_entry", ctx=ctx)  # IRREVERSIBLE_WRITE


def test_an_unknown_tool_fails_closed() -> None:
    with pytest.raises(KeyError):
        authorize_tool_call("teleport_funds", ctx=_ctx(Role.APPROVER))
