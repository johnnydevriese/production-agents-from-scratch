"""Steps ④–⑥ — the incident frozen as a regression case, red on buggy, green on fixed.

The case composes evaluators *defined in earlier chapters*; it invents no new
machinery. Each of the four diagnosed bugs becomes one check:

| Diagnosis | Check | Borrowed from |
|---|---|---|
| ① misroute        | `routed_to_ap`                 | the routing layer (Ch 13–14) |
| ② over-broad menu | `money_movement_only_under_ap` | tool scoping (Ch 12) |
| ④ double-pay      | `paid_exactly_once`            | `ToolCallCount` (Ch 20) |
| ③ empty key       | `payment_has_idempotency_key`  | the idempotency contract (Ch 26) |

`paid_exactly_once` runs Chapter 20's real `ToolCallCount` over a span tree captured
from the **real** Chapter 11 autopilot driven by a `FunctionModel` — so a red is
proof the *agent* double-paid, not a fixture. The buggy run reproduces all four
failures; the fixed run clears all four. Deleting one fix at a time (the chapter's
"Try it yourself") is just dropping one check back to red — and defense in depth
means the double-pay only reappears once the *idempotency* fix is the one removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_evals.otel.span_tree import SpanTree

from autopilot import InvoiceId, Payment, Specialist
from autopilot.fixtures import INVOICES
from ch11_framework.agent import Deps, autopilot
from ch20_structural.evaluators import ToolCallCount
from ch20_structural.harness import RecordingTools, capture_tree, context_for
from ch26_durable.idempotency import payment_idempotency_key

_INVOICE = INVOICES[InvoiceId("INV-1043")]
_STABLE_KEY = payment_idempotency_key(_INVOICE)


class _PaymentRecordingTools(RecordingTools):
    """The Chapter 20 boundary fake, extended to keep the `Payment` objects so the
    idempotency-key check can read the key the agent actually passed."""

    def __init__(self) -> None:
        super().__init__()
        self.payments: list[Payment] = []

    def schedule_payment(
        self, invoice_id: InvoiceId, *, idempotency_key: str
    ) -> Payment:
        payment = super().schedule_payment(invoice_id, idempotency_key=idempotency_key)
        self.payments.append(payment)
        return payment


def _script(tool_calls: list[tuple[str, dict[str, Any]]]) -> FunctionModel:
    """One tool call per turn, then a final answer — the Chapter 20 discipline (one
    per response, so the dispatch order is deterministic)."""
    state = {"turn": 0}

    def fn(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        turn = state["turn"]
        state["turn"] += 1
        if turn < len(tool_calls):
            name, args = tool_calls[turn]
            return ModelResponse(parts=[ToolCallPart(tool_name=name, args=args)])
        return ModelResponse(parts=[TextPart(content="Done. INV-1043 handled.")])

    return FunctionModel(fn)


@dataclass(frozen=True)
class IncidentRun:
    """One reproduction: where the request routed, the span tree it produced, and the
    payments it emitted. A value object carrying a non-pydantic `SpanTree`."""

    route: Specialist
    tree: SpanTree
    tools_called: tuple[str, ...]
    payments: tuple[Payment, ...]


class IncidentReport(BaseModel):
    """The four checks the incident case asserts — every one red on Tuesday's code."""

    routed_to_ap: bool
    money_movement_only_under_ap: bool
    paid_exactly_once: bool
    payment_has_idempotency_key: bool

    @property
    def passed(self) -> bool:
        return all(self.model_dump().values())

    @property
    def failures(self) -> list[str]:
        return [name for name, ok in self.model_dump().items() if not ok]


def check_incident(run: IncidentRun) -> IncidentReport:
    """Run the four borrowed checks over one reproduction."""
    paid_once = ToolCallCount("schedule_payment", expected_count=1).evaluate(
        context_for(run.tree)
    )
    return IncidentReport(
        routed_to_ap=run.route is Specialist.AP,
        money_movement_only_under_ap=(
            run.route is Specialist.AP or "schedule_payment" not in run.tools_called
        ),
        paid_exactly_once=paid_once is True,
        payment_has_idempotency_key=all(bool(p.idempotency_key) for p in run.payments),
    )


def _run(
    *, route: Specialist, tool_calls: list[tuple[str, dict[str, Any]]]
) -> IncidentRun:
    tools = _PaymentRecordingTools()
    deps = Deps(tools=tools, confirmed=True)
    with autopilot.override(model=_script(tool_calls)):
        tree = capture_tree(autopilot, INCIDENT_REQUEST, deps=deps)
    return IncidentRun(
        route=route,
        tree=tree,
        tools_called=tuple(tools.calls),
        payments=tuple(tools.payments),
    )


INCIDENT_REQUEST = "Please pay invoice #1043 from Acme."

_AMOUNT = float(_INVOICE.total)
_GL_ENTRY = {
    "invoice_id": "INV-1043",
    "debit_account": "5000-Engineering",
    "credit_account": "2000-AP",
    "amount": str(_INVOICE.total),
}


def buggy_run() -> IncidentRun:
    """Tuesday's code: misrouted to reporting, double-paid with empty keys."""
    return _run(
        route=Specialist.REPORTING,
        tool_calls=[
            ("check_budget", {"department": "Engineering", "amount": _AMOUNT}),
            ("schedule_payment", {"invoice_id": "INV-1043", "idempotency_key": ""}),
            ("schedule_payment", {"invoice_id": "INV-1043", "idempotency_key": ""}),
        ],
    )


# The path after the infrastructure fix: matched, in-budget, approved, paid ONCE
# with a threaded key, then booked. Used by both the fully-fixed run and the
# "silent variant" below, which keeps this path but drops the routing/scoping fix.
_KEYED_SINGLE_PAY: list[tuple[str, dict[str, Any]]] = [
    ("match_to_po", {"invoice_id": "INV-1043"}),
    ("check_budget", {"department": "Engineering", "amount": _AMOUNT}),
    ("request_approval", {"invoice_id": "INV-1043", "reason": "high value"}),
    ("schedule_payment", {"invoice_id": "INV-1043", "idempotency_key": _STABLE_KEY}),
    ("post_journal_entry", {"entry": _GL_ENTRY}),
]


def fixed_run() -> IncidentRun:
    """After the three-layer fix: routed to AP, paid once, with a threaded key."""
    return _run(route=Specialist.AP, tool_calls=_KEYED_SINGLE_PAY)


def silent_variant_run() -> IncidentRun:
    """Drop only the routing/scoping fix, keep the idempotency one: the wrong agent
    now pays *correctly once*. No double-pay reaches a human inbox, so the loud
    symptom is gone — but the real defect survives, caught only by the scoping check,
    never by luck. This is why the silent fix is the dangerous one to remove."""
    return _run(route=Specialist.REPORTING, tool_calls=_KEYED_SINGLE_PAY)
