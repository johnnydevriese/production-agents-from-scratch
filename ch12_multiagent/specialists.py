"""The autopilot, split into specialists — each a (prompt, tool-menu) pair.

The opening bug — a *report* request that scheduled a *payment* — was a context-
and-menu problem: one overloaded agent's single tool menu put `schedule_payment`
one token from `lookup_invoice`. The fix is structural, not a better prompt: give
each specialist its OWN prompt and its OWN slice of the frozen tool menu. The
reporting specialist has no `schedule_payment` in its menu, so no sampling outcome
can pay an invoice — the capability is simply absent from the agent that handles
reports.

`TOOLS_BY_SPECIALIST` is that menu as data: read a row and you see exactly what an
agent may do. Money movement (`schedule_payment`, `post_journal_entry`) appears in
exactly one row — AP — and nowhere else.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from pydantic_ai import Agent, RunContext

from autopilot import (
    ApprovalRequest,
    AutopilotTools,
    BudgetCheck,
    Invoice,
    InvoiceId,
    JournalEntry,
    MatchResult,
    Payment,
    Specialist,
    Vendor,
    VendorId,
)

MODEL = "anthropic:claude-sonnet-4-6"


@dataclass
class Deps:
    """The Chapter 6 facade, injected. Every specialist shares one tool backend and
    differs only in which slice of it its menu reaches."""

    tools: AutopilotTools


def lookup_invoice(ctx: RunContext[Deps], invoice_id: InvoiceId) -> Invoice:
    """Fetch an invoice record. Read-only."""
    return ctx.deps.tools.lookup_invoice(invoice_id)


def get_vendor(ctx: RunContext[Deps], vendor_id: VendorId) -> Vendor:
    """Fetch vendor and bank details. Read-only."""
    return ctx.deps.tools.get_vendor(vendor_id)


def match_to_po(ctx: RunContext[Deps], invoice_id: InvoiceId) -> MatchResult:
    """Match an invoice to its purchase order; flag exceptions. Read-only."""
    return ctx.deps.tools.match_to_po(invoice_id)


def check_budget(
    ctx: RunContext[Deps], *, department: str, amount: Decimal
) -> BudgetCheck:
    """Is this amount within a department's budget? Read-only."""
    return ctx.deps.tools.check_budget(department=department, amount=amount)


def request_approval(
    ctx: RunContext[Deps], invoice_id: InvoiceId, reason: str
) -> ApprovalRequest:
    """Ask a human to weigh in. External comms."""
    return ctx.deps.tools.request_approval(invoice_id, reason=reason)


def schedule_payment(
    ctx: RunContext[Deps], invoice_id: InvoiceId, idempotency_key: str
) -> Payment:
    """Pay a matched, approved, in-budget invoice. Money movement."""
    return ctx.deps.tools.schedule_payment(invoice_id, idempotency_key=idempotency_key)


def post_journal_entry(ctx: RunContext[Deps], entry: JournalEntry) -> JournalEntry:
    """Book the GL effect of a payment. Irreversible write."""
    return ctx.deps.tools.post_journal_entry(entry)


# The tool menu, as data — each specialist gets ONLY its row. Money movement lives
# in the AP row alone; remove a tool from a row and that action becomes impossible
# for that agent, no matter how it's prompted.
TOOLS_BY_SPECIALIST: dict[Specialist, tuple[Callable[..., object], ...]] = {
    Specialist.AP: (
        lookup_invoice,
        get_vendor,
        match_to_po,
        check_budget,
        request_approval,
        schedule_payment,
        post_journal_entry,
    ),
    Specialist.RECONCILIATION: (lookup_invoice, get_vendor, match_to_po),
    Specialist.REPORTING: (lookup_invoice, check_budget),  # ← no money-movement tool
    Specialist.VENDOR_MGMT: (get_vendor, request_approval),
}

PROMPTS: dict[Specialist, str] = {
    Specialist.AP: (
        "You are the accounts-payable specialist. Match invoices to POs, check "
        "budgets, request human approval, and — only when everything lines up — "
        "schedule payment."
    ),
    Specialist.RECONCILIATION: (
        "You are the reconciliation specialist. Match statements and invoices to "
        "purchase orders and surface discrepancies. You read data; you never pay."
    ),
    Specialist.REPORTING: (
        "You are the reporting analyst. Explain spend and budget variance. You "
        "read data; you never change it."
    ),
    Specialist.VENDOR_MGMT: (
        "You are the vendor-management specialist. Handle onboarding and bank-"
        "detail changes, escalating every change to a human for approval."
    ),
}


def _build(specialist: Specialist) -> Agent[Deps, str]:
    agent = Agent(MODEL, deps_type=Deps, system_prompt=PROMPTS[specialist])
    for tool in TOOLS_BY_SPECIALIST[specialist]:
        agent.tool(tool)
    return agent


SPECIALISTS: dict[Specialist, Agent[Deps, str]] = {
    specialist: _build(specialist) for specialist in Specialist
}
