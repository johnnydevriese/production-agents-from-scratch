"""GL coding as a typed classification, and the cascade that keeps the teacher honest.

These pin: the output is constrained to the chart of accounts; the student
classifies from invoice features; the cascade keeps confident student guesses and
falls up to the teacher only when unsure; the threshold `tau` is the dial; a coding
fills the *canonical* `JournalEntry` (no new tool); and the frontier teacher runs
offline under a `FunctionModel`. Zero spend.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from autopilot.fixtures import INVOICES, VENDORS
from autopilot.models import Invoice, InvoiceId, JournalEntry, Vendor, VendorId

from .gl_coder import (
    GL_SYSTEM,
    CascadingGLCoder,
    DistilledGLCoder,
    FrontierGLCoder,
    GLAccount,
    GLCoder,
    GLCoding,
    features,
    to_journal_entry,
)

_INVOICE = INVOICES[InvoiceId("INV-1043")]
_VENDOR = VENDORS[VendorId("V-ACME")]


def _coding(account: GLAccount, *, confidence: float) -> GLCoding:
    return GLCoding(debit_account=account, confidence=confidence, rationale="test")


class _StubSmallModel:
    """A deterministic stand-in for the served adapter: same features → same coding."""

    def __init__(self, coding: GLCoding) -> None:
        self._coding = coding
        self.seen: list[str] = []

    def classify(self, features: str) -> GLCoding:
        self.seen.append(features)
        return self._coding


class _RecordingCoder:
    """A `GLCoder` with a call counter, so a test can prove who got invoked."""

    def __init__(self, coding: GLCoding) -> None:
        self._coding = coding
        self.calls = 0

    def code(self, *, invoice: Invoice, vendor: Vendor) -> GLCoding:
        self.calls += 1
        return self._coding


def test_gl_coding_is_constrained_to_the_chart_of_accounts() -> None:
    # An account outside the fixed label space is impossible by construction (Ch 9).
    with pytest.raises(ValidationError):
        GLCoding(debit_account="9999", confidence=0.9, rationale="off-chart")  # type: ignore[arg-type]


def test_the_student_classifies_from_invoice_features() -> None:
    model = _StubSmallModel(_coding(GLAccount.SOFTWARE_SAAS, confidence=0.96))
    student: GLCoder = DistilledGLCoder(model=model)
    coding = student.code(invoice=_INVOICE, vendor=_VENDOR)

    assert coding.debit_account is GLAccount.SOFTWARE_SAAS
    assert model.seen == [features(_INVOICE, _VENDOR)]  # it fed the features in


def test_the_cascade_keeps_confident_student_guesses_and_skips_the_teacher() -> None:
    student = _RecordingCoder(_coding(GLAccount.SOFTWARE_SAAS, confidence=0.97))
    teacher = _RecordingCoder(_coding(GLAccount.SUPPLIES, confidence=1.0))
    cascade = CascadingGLCoder(student=student, teacher=teacher, tau=0.90)

    coding = cascade.code(invoice=_INVOICE, vendor=_VENDOR)
    assert coding.debit_account is GLAccount.SOFTWARE_SAAS  # the cheap student path
    assert teacher.calls == 0  # the teacher was never called


def test_the_cascade_falls_up_to_the_teacher_when_the_student_is_unsure() -> None:
    student = _RecordingCoder(_coding(GLAccount.SOFTWARE_SAAS, confidence=0.50))
    teacher = _RecordingCoder(_coding(GLAccount.PROFESSIONAL, confidence=0.99))
    cascade = CascadingGLCoder(student=student, teacher=teacher, tau=0.90)

    coding = cascade.code(invoice=_INVOICE, vendor=_VENDOR)
    assert (
        coding.debit_account is GLAccount.PROFESSIONAL
    )  # the hard tail, kept for the teacher
    assert teacher.calls == 1


def test_the_threshold_is_the_dial() -> None:
    # The SAME student guess (conf=0.85) is kept or escalated purely by where tau sits.
    strict_student = _RecordingCoder(_coding(GLAccount.SUPPLIES, confidence=0.85))
    strict_teacher = _RecordingCoder(_coding(GLAccount.PROFESSIONAL, confidence=1.0))
    strict = CascadingGLCoder(student=strict_student, teacher=strict_teacher, tau=0.90)
    assert (
        strict.code(invoice=_INVOICE, vendor=_VENDOR).debit_account
        is GLAccount.PROFESSIONAL
    )
    assert strict_teacher.calls == 1  # safer, costlier

    lenient_student = _RecordingCoder(_coding(GLAccount.SUPPLIES, confidence=0.85))
    lenient_teacher = _RecordingCoder(_coding(GLAccount.PROFESSIONAL, confidence=1.0))
    lenient = CascadingGLCoder(
        student=lenient_student, teacher=lenient_teacher, tau=0.80
    )
    assert (
        lenient.code(invoice=_INVOICE, vendor=_VENDOR).debit_account
        is GLAccount.SUPPLIES
    )
    assert lenient_teacher.calls == 0  # cheaper, riskier


def test_a_coding_fills_the_canonical_journal_entry_unchanged() -> None:
    coding = _coding(GLAccount.SOFTWARE_SAAS, confidence=0.96)
    entry = to_journal_entry(coding, invoice=_INVOICE)

    assert isinstance(entry, JournalEntry)
    assert entry.invoice_id == _INVOICE.id
    assert entry.debit_account == "6200"  # GLAccount.SOFTWARE_SAAS.value
    assert entry.credit_account == "2000"  # the standard AP credit side
    assert entry.amount == _INVOICE.total


def _teacher_emitting(coding: GLCoding) -> FunctionModel:
    def model_fn(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        out = (info.output_tools or [])[0].name
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=out,
                    args={
                        "debit_account": coding.debit_account.value,
                        "credit_account": coding.credit_account.value,
                        "confidence": coding.confidence,
                        "rationale": coding.rationale,
                    },
                )
            ]
        )

    return FunctionModel(model_fn)


def test_the_frontier_teacher_returns_a_coding_offline() -> None:
    agent: Agent[None, GLCoding] = Agent(
        "anthropic:claude-sonnet-4-6", output_type=GLCoding, system_prompt=GL_SYSTEM
    )
    teacher = FrontierGLCoder(agent=agent)
    scripted = _coding(GLAccount.SOFTWARE_SAAS, confidence=0.97)
    with agent.override(model=_teacher_emitting(scripted)):
        coding = teacher.code(invoice=_INVOICE, vendor=_VENDOR)
    assert coding.debit_account is GLAccount.SOFTWARE_SAAS
    assert coding.confidence == pytest.approx(0.97)
