"""The machinery that makes the rule real: test the agent, mock only the boundary.

`capture_tree` runs the **real** agent — real system prompt, real tool schemas,
real loop — under instrumentation, and returns the span tree it produced. The model
is driven by a `FunctionModel` in tests (offline, zero spend, Chapter 20's two
rules), but the model is never *scripted into the assertions*: the agent's loop and
tool dispatch produce the spans, so the evaluators score the agent's behavior, not a
fixture's.

What we *do* mock is the boundary — the tool implementations. `RecordingTools` is
the in-memory fake the chapter describes: it records each call and returns a canned,
valid domain object. In the full-stack lane these are the real services against a
sandbox ledger; here they are fakes. Either way the *model* is real.

The instrumentation is bound to a fresh local `TracerProvider` per run via
`InstrumentationSettings(tracer_provider=...)` — never the global provider — so
capture is isolated and two runs in one process can't cross-contaminate.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, TypeVar

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from pydantic_ai import Agent, InstrumentationSettings
from pydantic_evals.evaluators import EvaluatorContext
from pydantic_evals.otel.span_tree import SpanTree

from autopilot import (
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
from autopilot.fixtures import INVOICES, VENDORS

DepsT = TypeVar("DepsT")

_VALUE_DATE = date(2026, 7, 12)


class RecordingTools:
    """A boundary fake implementing `AutopilotTools`: records each call and returns a
    canned valid object. It enforces no business rules — any scripted path runs to
    completion and emits spans, which is exactly what the structural evals read."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __repr__(self) -> str:
        return f"RecordingTools(calls={self.calls!r})"

    def lookup_invoice(self, invoice_id: InvoiceId) -> Invoice:
        self.calls.append("lookup_invoice")
        return INVOICES[invoice_id]

    def get_vendor(self, vendor_id: VendorId) -> Vendor:
        self.calls.append("get_vendor")
        return VENDORS[vendor_id]

    def match_to_po(self, invoice_id: InvoiceId) -> MatchResult:
        self.calls.append("match_to_po")
        return MatchResult(invoice_id=invoice_id, matched=True)

    def check_budget(self, *, department: str, amount: Decimal) -> BudgetCheck:
        self.calls.append("check_budget")
        return BudgetCheck(
            department=department,
            amount=Decimal(str(amount)),
            budget_remaining=Decimal("1011.91"),
            within_budget=True,
        )

    def request_approval(
        self, invoice_id: InvoiceId, *, reason: str
    ) -> ApprovalRequest:
        self.calls.append("request_approval")
        return ApprovalRequest(invoice_id=invoice_id, reason=reason, approver="cfo")

    def schedule_payment(
        self, invoice_id: InvoiceId, *, idempotency_key: str
    ) -> Payment:
        self.calls.append("schedule_payment")
        return Payment(
            invoice_id=invoice_id,
            amount=Decimal("2988.09"),
            idempotency_key=idempotency_key,
            scheduled_for=_VALUE_DATE,
        )

    def post_journal_entry(self, entry: JournalEntry) -> JournalEntry:
        self.calls.append("post_journal_entry")
        return entry


def capture_tree(agent: Agent[DepsT, str], prompt: str, *, deps: DepsT) -> SpanTree:
    """Run the real agent under instrumentation and return its span tree."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    agent.instrument = InstrumentationSettings(tracer_provider=provider)
    agent.run_sync(prompt, deps=deps)
    provider.force_flush()
    tree = SpanTree()
    tree.add_readable_spans(list(exporter.get_finished_spans()))
    return tree


def context_for(tree: SpanTree) -> EvaluatorContext[Any, Any]:
    """Wrap a captured tree in an `EvaluatorContext` so the evaluators can run it.
    Only `span_tree` is load-bearing for structural evals; the rest are placeholders."""
    return EvaluatorContext(
        name=None,
        inputs=None,
        metadata=None,
        expected_output=None,
        output=None,
        duration=0.0,
        _span_tree=tree,  # pyright: ignore[reportPrivateUsage]
        attributes={},
        metrics={},
    )
