"""A two-hop handoff — reconciliation → AP — carrying a TYPED payload.

The classic multi-agent bug is each agent re-deriving the previous agent's work
from a prose summary, and disagreeing. The fix is to hand off the *validated
domain object*, not a paragraph. Reconciliation emits a `MatchResult`
(`output_type=MatchResult`); the supervisor passes that exact object into AP's
deps; AP settles the invoice the `MatchResult` names — it never re-reads "recon
says it looks fine."

Durability — an audit trail, idempotency on the money leg, a ceiling on hops —
arrives in Chapter 26. This shows only the data contract.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from autopilot import AutopilotTools, MatchResult, Payment

from .specialists import MODEL


@dataclass
class APHandoff:
    """AP's deps for a handoff: the facade PLUS the typed `MatchResult` from
    reconciliation. AP reads `match` — a validated object — never a prose summary."""

    tools: AutopilotTools
    match: MatchResult


reconciliation_agent = Agent(
    MODEL,
    output_type=MatchResult,  # the handoff payload is a typed object by construction
    system_prompt="Reconcile the invoice against its PO and report the match result.",
)

ap_agent = Agent(
    MODEL,
    deps_type=APHandoff,
    system_prompt="Settle the reconciled invoice the handoff names.",
)


@ap_agent.tool
def settle(ctx: RunContext[APHandoff], idempotency_key: str) -> Payment:
    """Pay the invoice reconciliation matched. The invoice id comes from the typed
    handoff (`ctx.deps.match`), not from anything the model re-derived."""
    return ctx.deps.tools.schedule_payment(
        ctx.deps.match.invoice_id, idempotency_key=idempotency_key
    )


async def reconcile_then_settle(
    invoice_id: str, *, facade: AutopilotTools
) -> str | None:
    """Supervisor: reconcile, then settle only on a clean match. A discrepancy holds
    the payment for a human — the money leg never runs."""
    match = (await reconciliation_agent.run(f"Reconcile {invoice_id}")).output
    if not match.matched or match.discrepancies:
        return None
    deps = APHandoff(tools=facade, match=match)
    result = await ap_agent.run("Settle it.", deps=deps)
    return result.output
