"""GL coding as classification behind a typed interface — teacher, student, cascade.

The autopilot calls a frontier model on *every* invoice just to pick the
general-ledger accounts for `post_journal_entry`. That step is a fixed-label
classification (vendor + line items → an account from the chart), it's high-volume,
and accountants already grade it on the approval screen. So it's a distillation
candidate: train a small student to execute the repetitive 96%, keep the frontier
teacher for the hard tail, and decide between them with a confidence threshold.

Every coder satisfies the same `GLCoder` Protocol, so swapping the implementation
changes nothing downstream — and we did *not* invent a new tool: GL coding fills the
`debit_account`/`credit_account` of the canonical `JournalEntry`; the gated
`post_journal_entry` is unchanged (`to_journal_entry`).
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from autopilot.models import Invoice, JournalEntry, Vendor


class GLAccount(str, Enum):
    """The fixed label space — a (tiny) chart of accounts. The real one has hundreds;
    the point is that it is *finite and fixed*, which makes this a classification."""

    SUPPLIES = "6100"
    SOFTWARE_SAAS = "6200"
    PROFESSIONAL = "6300"
    FREIGHT = "6400"
    ACCOUNTS_PAYABLE = "2000"  # the credit side for a standard AP invoice


class GLCoding(BaseModel):
    """Structured output (Ch 9): one row of a `JournalEntry`, with a confidence the
    cascade reads to decide whether to trust the student."""

    debit_account: GLAccount
    credit_account: GLAccount = GLAccount.ACCOUNTS_PAYABLE
    confidence: float = Field(ge=0.0, le=1.0)  # below the cascade's threshold → a human
    rationale: str


class GLCoder(Protocol):
    """Every coder is interchangeable behind this — teacher, student, or cascade."""

    def code(self, *, invoice: Invoice, vendor: Vendor) -> GLCoding: ...


def features(invoice: Invoice, vendor: Vendor) -> str:
    """The classifier's input: vendor, currency, total, and line-item descriptions.

    Bank details never enter the features: `repr=False` helps log hygiene on
    `Vendor`, and the feature builder simply does not read those fields — the same
    secrets discipline as Ch 29.
    """
    line_items = "; ".join(item.description for item in invoice.line_items)
    return (
        f"vendor={vendor.name}; currency={invoice.currency}; "
        f"total={invoice.total}; line_items={line_items}"
    )


def to_journal_entry(coding: GLCoding, *, invoice: Invoice) -> JournalEntry:
    """Fill the canonical `JournalEntry` from a coding — no new tool, no new write.

    We swap *who computes a step's inputs*, not the bounded tool menu; the
    irreversible `post_journal_entry` still books this entry under the Ch 3 gate.
    """
    return JournalEntry(
        invoice_id=invoice.id,
        debit_account=coding.debit_account.value,
        credit_account=coding.credit_account.value,
        amount=invoice.total,
    )


GL_SYSTEM = (
    "You assign general-ledger accounts to a finance-ops invoice.\n"
    "Pick ONE debit account from the chart of accounts that best fits the vendor and "
    "line items. The credit account is 2000 (Accounts Payable) for a standard "
    "invoice. Report a calibrated confidence and a one-line rationale."
)


class SmallModel(Protocol):
    """A served small classifier: features in, a coding with a calibrated prob out.

    A real one is a LoRA-adapted small open model behind a local endpoint (README);
    a test passes a deterministic stand-in, so the student is exercised offline.
    """

    def classify(self, features: str) -> GLCoding: ...


class DistilledGLCoder:
    """The student — a small fine-tuned classifier. Milliseconds, ~$0, deterministic."""

    def __init__(self, *, model: SmallModel) -> None:
        self._model = model

    def __repr__(self) -> str:
        return "DistilledGLCoder()"

    def code(self, *, invoice: Invoice, vendor: Vendor) -> GLCoding:
        return self._model.classify(features(invoice, vendor))


class FrontierGLCoder:
    """The teacher — a full frontier generation, every invoice. What we have today."""

    def __init__(self, *, agent: Agent[None, GLCoding]) -> None:
        self._agent = agent

    def __repr__(self) -> str:
        return "FrontierGLCoder()"

    def code(self, *, invoice: Invoice, vendor: Vendor) -> GLCoding:
        return self._agent.run_sync(features(invoice, vendor)).output


def build_frontier_gl_coder(
    model: str = "anthropic:claude-sonnet-5",
) -> FrontierGLCoder:
    """Construct the teacher: a PydanticAI agent with structured output (Ch 9, 11)."""
    return FrontierGLCoder(
        agent=Agent(model, output_type=GLCoding, system_prompt=GL_SYSTEM)
    )


class CascadingGLCoder:
    """Run the student first; fall *up* to the teacher only when it's unsure.

    The threshold `tau` is the entire safety story and a dial against the asymmetric
    cost (Ch 13): a wrong account on a routine supplies invoice is a cheap fix; a
    wrong account on a six-figure capital item distorts the financials. Set it high
    and more invoices fall up (safer, costlier); low and the student keeps more
    (cheaper, riskier). Every fall-up still hits the accountant's review, so the
    cascade keeps generating corrections — it is also a data flywheel.
    """

    def __init__(
        self, *, student: GLCoder, teacher: GLCoder, tau: float = 0.90
    ) -> None:
        self._student = student
        self._teacher = teacher
        self._tau = tau

    def __repr__(self) -> str:
        return f"CascadingGLCoder(tau={self._tau})"

    def code(self, *, invoice: Invoice, vendor: Vendor) -> GLCoding:
        guess = self._student.code(invoice=invoice, vendor=vendor)
        if guess.confidence >= self._tau:
            return guess  # the cheap path: the ~95% the student owns
        return self._teacher.code(invoice=invoice, vendor=vendor)  # fall up when unsure
