"""The autopilot agent whose ROUTING the system prompt controls.

Same seven tools as Chapter 6 (delegated to that chapter's facade); what changes
here is the *prompt*, loaded by version from the registry as the agent's
instructions. `run_autopilot` runs the agent and returns the tool-call PATH (the
span trace of Chapter 4), so a test can assert what the agent DID — not how its
summary reads.

The default model is a deterministic stand-in for a literal-minded LLM: it reads
the **actual instructions the agent sent** (`info.instructions`) and the invoice
text, and fires the tools the prompt's routing rules dictate. That is the
chapter's thesis made executable — the *prompt text* decides the path, so editing
the prompt file flips the test. A real run drops in by passing the provider model
to `run_autopilot(..., model=...)`; the wiring is identical.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel

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
from ch06_facade.facade import RailPaymentFacade
from ch06_facade.rail import FakeRail

from .prompt_registry import load_system_prompt


@dataclass
class AutopilotDeps:
    """What a run carries: the execution facade and which prompt version is live."""

    facade: RailPaymentFacade
    prompt_version: str


class ToolSpan(BaseModel):
    tool_name: str


class Trace(BaseModel):
    """The tool-call path of one run — what the agent DID, not what it said."""

    tool_spans: list[ToolSpan]


autopilot_agent = Agent(
    "anthropic:claude-sonnet-4-6",  # base model for a live run; tests override it
    deps_type=AutopilotDeps,
)


@autopilot_agent.instructions
def system_instructions(ctx: RunContext[AutopilotDeps]) -> str:
    return load_system_prompt(ctx.deps.prompt_version)


@autopilot_agent.tool
def lookup_invoice(ctx: RunContext[AutopilotDeps], invoice_id: str) -> Invoice:
    """Fetch an invoice record by its ID. Read-only."""
    return ctx.deps.facade.lookup_invoice(InvoiceId(invoice_id))


@autopilot_agent.tool
def get_vendor(ctx: RunContext[AutopilotDeps], vendor_id: str) -> Vendor:
    """Fetch a vendor record by its ID. Read-only."""
    return ctx.deps.facade.get_vendor(VendorId(vendor_id))


@autopilot_agent.tool
def match_to_po(ctx: RunContext[AutopilotDeps], invoice_id: str) -> MatchResult:
    """Three-way match an invoice to its PO. A missing PO is an exception. Read-only."""
    return ctx.deps.facade.match_to_po(InvoiceId(invoice_id))


@autopilot_agent.tool
def check_budget(
    ctx: RunContext[AutopilotDeps], department: str, amount: Decimal
) -> BudgetCheck:
    """Is this amount within a department's budget? Read-only."""
    return ctx.deps.facade.check_budget(department=department, amount=amount)


@autopilot_agent.tool
def request_approval(
    ctx: RunContext[AutopilotDeps], invoice_id: str, reason: str
) -> ApprovalRequest:
    """Ask a human to weigh in. External comms."""
    return ctx.deps.facade.request_approval(InvoiceId(invoice_id), reason=reason)


@autopilot_agent.tool
def schedule_payment(
    ctx: RunContext[AutopilotDeps], invoice_id: str, idempotency_key: str
) -> Payment:
    """Pay a matched, approved, in-budget invoice. Money movement."""
    return ctx.deps.facade.schedule_payment(
        InvoiceId(invoice_id), idempotency_key=idempotency_key
    )


@autopilot_agent.tool
def post_journal_entry(
    ctx: RunContext[AutopilotDeps], entry: JournalEntry
) -> JournalEntry:
    """Book the GL effect of a payment. Irreversible write."""
    return ctx.deps.facade.post_journal_entry(entry)


# --- The deterministic literal-prompt interpreter (the offline stand-in model) ---

_INVOICE_ID = re.compile(r"[Ii]nvoice\s*#?\s*([A-Z]{2,}-\d+)")
_PO_CUE = re.compile(r"\bP\.?O\.?[-\s#]?\d+\b|\bpurchase order\b", re.IGNORECASE)
_DEPT_BY_VENDOR = {VendorId("V-ACME"): "Engineering", VendorId("V-DOC"): "Operations"}


def _instructions(info: AgentInfo) -> str:
    return info.instructions or ""


def _first_user_text(messages: list[ModelMessage]) -> str:
    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                return part.content
    return ""


def _tools_called(messages: list[ModelMessage]) -> set[str]:
    return {
        part.tool_name
        for message in messages
        for part in getattr(message, "parts", [])
        if isinstance(part, ToolCallPart)
    }


def _last_invoice(messages: list[ModelMessage]) -> Invoice | None:
    found: Invoice | None = None
    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolReturnPart) and isinstance(part.content, Invoice):
                found = part.content
    return found


def _should_match(system_prompt: str, invoice_text: str) -> bool:
    text = system_prompt.lower()
    if "every invoice must be matched" in text or "always call match_to_po" in text:
        return True
    if "when the user provides a purchase order" in text:
        return bool(_PO_CUE.search(invoice_text))
    return False


def _tool_plan(system_prompt: str, invoice_text: str) -> list[str]:
    """The tools a literal model fires under this prompt, in order."""
    plan = ["lookup_invoice", "get_vendor"]
    if _should_match(system_prompt, invoice_text):
        plan.append("match_to_po")
    plan.append("check_budget")
    return plan


def _args_for(
    tool_name: str, *, invoice_id: str, invoice: Invoice | None
) -> dict[str, object] | None:
    if tool_name in ("lookup_invoice", "match_to_po"):
        return {"invoice_id": invoice_id}
    if tool_name == "get_vendor":
        return None if invoice is None else {"vendor_id": str(invoice.vendor_id)}
    if tool_name == "check_budget":
        if invoice is None:
            return None
        department = _DEPT_BY_VENDOR.get(invoice.vendor_id, "Operations")
        return {"department": department, "amount": str(invoice.total)}
    return None


def prompt_following_model() -> FunctionModel:
    """A literal-minded model: it follows the live prompt's routing rules over the
    invoice text. Reading the *prompt text* (not a version flag) is the point —
    edit the prompt and the path changes, exactly as a real model's would."""

    def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        system_prompt = _instructions(info)
        invoice_text = _first_user_text(messages)
        match = _INVOICE_ID.search(invoice_text)
        invoice_id = match.group(1) if match else "INV-1043"
        called = _tools_called(messages)
        invoice = _last_invoice(messages)

        for tool_name in _tool_plan(system_prompt, invoice_text):
            if tool_name in called:
                continue
            args = _args_for(tool_name, invoice_id=invoice_id, invoice=invoice)
            if args is not None:
                return ModelResponse(
                    parts=[ToolCallPart(tool_name=tool_name, args=args)]
                )
        return ModelResponse(
            parts=[TextPart(content="Invoice processed and routed per policy.")]
        )

    return FunctionModel(model_fn)


def run_autopilot(
    invoice_text: str, *, prompt_version: str, model: Model | None = None
) -> Trace:
    """Run the autopilot under a named prompt version; return its tool-call path."""
    deps = AutopilotDeps(
        facade=RailPaymentFacade(rail=FakeRail(value_date=date(2026, 7, 12))),
        prompt_version=prompt_version,
    )
    with autopilot_agent.override(model=model or prompt_following_model()):
        result = autopilot_agent.run_sync(invoice_text, deps=deps)
    spans = [
        ToolSpan(tool_name=part.tool_name)
        for message in result.all_messages()
        for part in getattr(message, "parts", [])
        if isinstance(part, ToolCallPart)
    ]
    return Trace(tool_spans=spans)


def main() -> None:
    trace = run_autopilot(
        "Invoice #DC-2207 — Janitorial services. Amount due: $1,840.00. Net 30.",
        prompt_version="v2",
    )
    print([span.tool_name for span in trace.tool_spans])


if __name__ == "__main__":
    main()
