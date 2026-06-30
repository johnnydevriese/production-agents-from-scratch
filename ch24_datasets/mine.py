"""Mining production: let the world write your hardest cases.

You will never imagine the distribution completely — the EUR/PO-less case lived in
production for months before it lived in the suite. The durable fix is to make
production *feed* the dataset: traces that smell wrong (low judge score, a human
correction, an `InvoiceStatus.EXCEPTION` the agent shouldn't have produced) become
candidates for triage.

Two rules keep mining from poisoning the suite, and both are enforced here:

1. **A correction is a signal, not ground truth.** A human who fixed one payment
   was solving *that* problem, not authoring a labeled example. `select_candidates`
   only flags traces; `promote_to_case` requires a person to supply the real
   `expected_tools` and `guards` — they are never lifted from the trace.
2. **Mined cases enter dev, not golden.** `promote_to_case` stamps `origin=MINED`,
   and `split.assert_golden_eligible` refuses it until it's been reviewed and
   reclassified.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

from autopilot import InvoiceId, InvoiceStatus

from .cases import EvalCase, Origin

_LOW_JUDGE_SCORE = 2  # 1–2 on the Ch 22 rubric = unusable / vague


class Trace(BaseModel):
    """A minimal production trace — the catching mechanics are Chapter 23's."""

    trace_id: str
    request: str
    invoice_id: InvoiceId | None = None
    tools_called: list[str] = Field(default_factory=list)
    judge_score: int | None = None  # Ch 22 pointwise grade, if scored
    human_corrected: bool = False
    final_status: InvoiceStatus | None = None


def is_candidate(trace: Trace) -> bool:
    return (
        (trace.judge_score is not None and trace.judge_score <= _LOW_JUDGE_SCORE)
        or trace.human_corrected
        or trace.final_status is InvoiceStatus.EXCEPTION
    )


def select_candidates(traces: Sequence[Trace]) -> list[Trace]:
    """Filter traces worth a human's attention. Most production traces are noise."""
    return [trace for trace in traces if is_candidate(trace)]


def promote_to_case(
    trace: Trace,
    *,
    expected_tools: Sequence[str],
    guards: str,
    forbidden_tools: Sequence[str] = (),
    answer_must_mention: Sequence[str] = (),
) -> EvalCase:
    """Author a MINED dev case from a triaged trace. The labels come from the human
    doing triage — never from `trace.tools_called`, which is what the agent *did*,
    not what it *should* have done."""
    return EvalCase(
        id=f"mined-{trace.trace_id}",
        request=trace.request,
        invoice_id=trace.invoice_id,
        expected_tools=list(expected_tools),
        forbidden_tools=list(forbidden_tools),
        answer_must_mention=list(answer_must_mention),
        origin=Origin.MINED,
        guards=guards,
        source_trace_id=trace.trace_id,
    )
