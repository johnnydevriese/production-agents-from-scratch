"""Score the garbage reason and the good one with the pointwise judge.

This is the one module here that makes a real model call — it is the "you can run
it" artifact for the chapter. The tests stay offline; this costs a couple of judge
tokens and needs a key:

    export ANTHROPIC_API_KEY=sk-...
    uv run python -m ch22_judge.demo

The grades and wording vary run-to-run — the judge is a model call, not an oracle.
A borderline reason can flip between a 3 and a 4; that variance is exactly why
calibration (`calibrate.py`) exists.
"""

from __future__ import annotations

from autopilot import ApprovalRequest, InvoiceId, MatchResult, PurchaseOrderId

from .reason_judge import Grade, Verdict, build_reason_judge, judge_reason

_FINDINGS = ["PO-3310 ordered 50 actuators; invoice bills 60 — quantity mismatch"]

_CASES: dict[InvoiceId, ApprovalRequest] = {
    InvoiceId("INV-7741"): ApprovalRequest(
        invoice_id=InvoiceId("INV-7741"),
        reason="This invoice requires manual review based on the analysis performed.",
        approver="ap-controller@northwind.example",
    ),
    InvoiceId("INV-7742"): ApprovalRequest(
        invoice_id=InvoiceId("INV-7742"),
        reason="PO-3310 ordered 50 actuators; invoice bills 60. Hold for procurement.",
        approver="ap-controller@northwind.example",
    ),
}


def _print_verdict(invoice_id: InvoiceId, verdict: Verdict) -> None:
    grade = Grade(verdict.grade)
    print(f"{invoice_id}  grade={grade.value} {grade.name}")
    print(f"  quote:  {verdict.evidence_quote!r}")
    print(f"  why:    {verdict.reasoning}")


def main() -> None:
    # A different model family than the agent under test would be ideal here
    # (self-enhancement bias); the reference app is Anthropic-only, so production
    # should swap this for the cheaper/different judge the economics section names.
    judge = build_reason_judge("anthropic:claude-sonnet-5")
    for invoice_id, approval in _CASES.items():
        match = MatchResult(
            invoice_id=invoice_id,
            matched=False,
            purchase_order_id=PurchaseOrderId("PO-3310"),
            discrepancies=_FINDINGS,
        )
        _print_verdict(invoice_id, judge_reason(approval, match, judge=judge))


if __name__ == "__main__":
    main()
