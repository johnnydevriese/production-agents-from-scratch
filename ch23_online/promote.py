"""The promote arrow: a confirmed-bad trace becomes a permanent offline case.

This is the whole chapter. A confirmed-bad trace carries everything needed to
reconstruct a deterministic case — the input invoice, the tool path it took — and
the human's verdict supplies the *correct* path it should have taken. We freeze
that into a real `ch24_datasets` `EvalCase`.

Two disciplines are enforced by the types, not by convention:

- The case is `origin=MINED` and carries `source_trace_id` — Chapter 24's own
  validator *rejects* a MINED case with no provenance, so a promoted case can't
  exist without citing the incident it came from.
- The path comes from the human's verdict, not the trace's `tools_called`: a
  correction is a *signal*, never ground truth lifted into an assertion. The
  promoted case asserts what *should* have happened (e.g. `request_approval`
  before any `schedule_payment`), which is exactly what the trace got wrong.

A fresh promoted case is therefore dev-only — `ch24`'s `assert_golden_eligible`
holds it out of the golden set until a second, independent human reviews it.
"""

from __future__ import annotations

from ch24_datasets.cases import EvalCase, Origin

from .models import HumanVerdict, Trace


def trace_to_eval_case(trace: Trace, *, verdict: HumanVerdict) -> EvalCase:
    """Freeze a confirmed-bad production trace into an offline eval case."""
    return EvalCase(
        id=f"prod-{trace.id}",
        request=trace.request,
        invoice_id=trace.invoice.id,
        expected_tools=verdict.expected_tools,  # the human's path, not the trace's
        forbidden_tools=verdict.forbidden_tools,
        origin=Origin.MINED,
        guards=verdict.note,  # the provenance string — why this case exists
        source_trace_id=trace.id,  # the bug it came from, one click away
    )
