"""The bounded agent, wired with PydanticAI — the framework adopted from here on.

The model sees only the typed tools; each one delegates straight to the facade
(`ctx.deps`), so the messy rail stays invisible. PydanticAI generates the JSON
schema from the type hints and validates the model's arguments before our
function runs — the dispatch we hand-rolled in Chapter 3, now framework-owned.

    export ANTHROPIC_API_KEY=sk-...
    uv run python -m ch06_facade.agent
"""

from __future__ import annotations

from decimal import Decimal

from pydantic_ai import Agent, RunContext

from autopilot.models import (
    ApprovalRequest,
    BudgetCheck,
    Invoice,
    InvoiceId,
    JournalEntry,
    MatchResult,
    Payment,
    Vendor,
    VendorId,
)

from .facade import RailPaymentFacade

ap_agent = Agent(
    "anthropic:claude-sonnet-4-6",  # provider:model — same shape for openai:, google:
    deps_type=RailPaymentFacade,
    instructions=(
        "You are an accounts-payable autopilot. Before scheduling a payment, "
        "confirm the invoice is matched to a PO and within budget. Never invent "
        "an amount; read it with a tool."
    ),
)


@ap_agent.tool
def lookup_invoice(ctx: RunContext[RailPaymentFacade], invoice_id: str) -> Invoice:
    """Fetch an invoice record by its ID. Read-only."""
    return ctx.deps.lookup_invoice(InvoiceId(invoice_id))


@ap_agent.tool
def get_vendor(ctx: RunContext[RailPaymentFacade], vendor_id: str) -> Vendor:
    """Fetch a vendor record by its ID. Read-only."""
    return ctx.deps.get_vendor(VendorId(vendor_id))


@ap_agent.tool
def match_to_po(ctx: RunContext[RailPaymentFacade], invoice_id: str) -> MatchResult:
    """Three-way match an invoice to its purchase order. Read-only."""
    return ctx.deps.match_to_po(InvoiceId(invoice_id))


@ap_agent.tool
def check_budget(
    ctx: RunContext[RailPaymentFacade], department: str, amount: Decimal
) -> BudgetCheck:
    """Is this amount within a department's budget? Read-only."""
    return ctx.deps.check_budget(department=department, amount=amount)


@ap_agent.tool
def request_approval(
    ctx: RunContext[RailPaymentFacade], invoice_id: str, reason: str
) -> ApprovalRequest:
    """Ask a human to weigh in. External comms."""
    return ctx.deps.request_approval(InvoiceId(invoice_id), reason=reason)


@ap_agent.tool
def schedule_payment(
    ctx: RunContext[RailPaymentFacade], invoice_id: str, idempotency_key: str
) -> Payment:
    """Pay a matched, approved, in-budget invoice. Money movement."""
    return ctx.deps.schedule_payment(
        InvoiceId(invoice_id), idempotency_key=idempotency_key
    )


@ap_agent.tool
def post_journal_entry(
    ctx: RunContext[RailPaymentFacade], entry: JournalEntry
) -> JournalEntry:
    """Book the GL effect of a payment. Irreversible write."""
    return ctx.deps.post_journal_entry(entry)


def main() -> None:
    from datetime import date

    from .rail import FakeRail

    facade = RailPaymentFacade(rail=FakeRail(value_date=date(2026, 7, 12)))
    result = ap_agent.run_sync(
        "Is invoice INV-1043 matched and within the Engineering budget?",
        deps=facade,
    )
    print(result.output)


if __name__ == "__main__":
    main()
