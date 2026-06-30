"""ch24 — the dataset as a first-class artifact. Pure, offline, no model.

These pin the chapter's claims: a case cannot exist without naming what it guards,
the coverage matrix counts *cells* (so the green suite's empty non-USD column is
visible), the dev/golden wall is stable and enforceable, and mining produces
human-authored dev cases, never auto-promoted assertions.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from autopilot import InvoiceId, InvoiceStatus

from .cases import EvalCase, Origin
from .coverage import AUTOPILOT_DIMENSIONS, build_report, report_for_cases
from .dataset import CASES
from .mine import Trace, promote_to_case, select_candidates
from .split import (
    LeakageError,
    PrematurePromotionError,
    assert_golden_eligible,
    assert_no_leakage,
    split_dev_golden,
)


def _make(
    *,
    id: str = "c1",
    guards: str = "baseline happy path.",
    origin: Origin = Origin.HANDWRITTEN,
    source_trace_id: str | None = None,
) -> EvalCase:
    return EvalCase(
        id=id,
        request="Pay invoice INV-1043.",
        expected_tools=["lookup_invoice"],
        origin=origin,
        guards=guards,
        source_trace_id=source_trace_id,
    )


# --- the case unit: provenance is required by construction -----------------------


def test_a_case_without_guards_cannot_exist() -> None:
    # The load-bearing rule: no case enters the dataset without naming the failure
    # it prevents. An empty string is rejected by min_length...
    with pytest.raises(ValidationError):
        _make(guards="")
    # ...and an omitted field is rejected as required.
    with pytest.raises(ValidationError):
        EvalCase.model_validate(
            {
                "id": "c1",
                "request": "x",
                "expected_tools": ["lookup_invoice"],
                "origin": "handwritten",
            }
        )


def test_mined_case_must_cite_its_trace() -> None:
    with pytest.raises(ValidationError, match="source_trace_id"):
        _make(origin=Origin.MINED)


def test_a_regression_case_forbids_the_dangerous_act() -> None:
    # You can only test for an act's *absence* if a case exists where it's wrong.
    po_less = next(c for c in CASES if c.id == "po-less-eur-services")
    assert "schedule_payment" in po_less.forbidden_tools
    assert po_less.origin is Origin.REGRESSION


# --- coverage: cells filled, not rows counted ------------------------------------


def _green_suite_cells() -> list[tuple[str, ...]]:
    # The 142-case suite we shipped on: every case clean USD, an entire column empty.
    return (
        [("matched", "USD")] * 118 + [("mismatch", "USD")] * 18 + [("none", "USD")] * 6
    )


def test_green_suite_has_an_empty_non_usd_column() -> None:
    report = build_report(_green_suite_cells(), dimensions=AUTOPILOT_DIMENSIONS)
    assert report.total_cells == 6
    assert report.covered_cells == 3
    # Every non-USD cell — including the one that paged us — is a gap.
    non_usd_gaps = [cell for cell in report.gaps if cell[1] == "non-USD"]
    assert len(non_usd_gaps) == 3
    assert ("none", "non-USD") in report.gaps


def test_coverage_counts_cells_not_rows() -> None:
    # 142 rows, but only half the grid covered. Case count is not coverage.
    report = build_report(_green_suite_cells(), dimensions=AUTOPILOT_DIMENSIONS)
    assert sum(c.count for c in report.counts) == 142
    assert report.fraction_covered == pytest.approx(0.5)


def test_curated_dataset_fills_the_non_usd_column() -> None:
    report = report_for_cases(CASES, dimensions=AUTOPILOT_DIMENSIONS)
    covered = {tuple(c.cell) for c in report.counts if c.count > 0}
    assert ("matched", "non-USD") in covered  # the synthetic case
    assert ("none", "non-USD") in covered  # the regression that paged us
    assert ("none", "non-USD") not in report.gaps


def test_a_cell_outside_the_grid_is_rejected() -> None:
    with pytest.raises(ValueError, match="not in the grid"):
        build_report([("matched", "GBP")], dimensions=AUTOPILOT_DIMENSIONS)


# --- the dev / golden wall -------------------------------------------------------


def _synthetic_cases(n: int) -> list[EvalCase]:
    return [_make(id=f"case-{i}", guards=f"guards {i}") for i in range(n)]


def test_split_is_stable_across_runs() -> None:
    cases = _synthetic_cases(200)
    dev_a, gold_a = split_dev_golden(cases)
    dev_b, gold_b = split_dev_golden(cases)
    assert {c.id for c in dev_a} == {c.id for c in dev_b}
    assert {c.id for c in gold_a} == {c.id for c in gold_b}


def test_dev_and_golden_are_disjoint_and_complete() -> None:
    cases = _synthetic_cases(200)
    dev, golden = split_dev_golden(cases)
    assert_no_leakage(dev, golden)  # does not raise
    assert {c.id for c in dev} | {c.id for c in golden} == {c.id for c in cases}


def test_golden_is_about_thirty_percent() -> None:
    cases = _synthetic_cases(1000)
    _dev, golden = split_dev_golden(cases, golden_fraction=0.30)
    assert 0.25 <= len(golden) / len(cases) <= 0.35


def test_leakage_guard_raises_when_a_case_is_in_both_halves() -> None:
    shared = _make()
    with pytest.raises(LeakageError, match="c1"):
        assert_no_leakage([shared], [shared])


def test_a_fresh_mined_case_is_not_golden_eligible() -> None:
    mined = _make(origin=Origin.MINED, source_trace_id="trace-99")
    with pytest.raises(PrematurePromotionError):
        assert_golden_eligible(mined)
    # Once reviewed and reclassified as a regression, the wall lets it through.
    reviewed = mined.model_copy(update={"origin": Origin.REGRESSION})
    assert_golden_eligible(reviewed)  # does not raise


# --- mining: a correction is a signal, not ground truth --------------------------


def test_select_candidates_catches_the_right_signals() -> None:
    traces = [
        Trace(trace_id="t-low", request="x", judge_score=1),
        Trace(trace_id="t-fixed", request="x", judge_score=5, human_corrected=True),
        Trace(trace_id="t-exc", request="x", final_status=InvoiceStatus.EXCEPTION),
        Trace(trace_id="t-clean", request="x", judge_score=5),  # noise — dropped
    ]
    selected = {t.trace_id for t in select_candidates(traces)}
    assert selected == {"t-low", "t-fixed", "t-exc"}


def test_promote_authors_a_mined_dev_case_from_the_human_not_the_trace() -> None:
    trace = Trace(
        trace_id="t-2208",
        request="Pay invoice INV-2208.",
        invoice_id=InvoiceId("INV-2208"),
        tools_called=[
            "lookup_invoice",
            "match_to_po",
            "schedule_payment",
        ],  # what it DID
        judge_score=1,
    )
    case = promote_to_case(
        trace,
        expected_tools=["lookup_invoice", "match_to_po", "request_approval"],  # SHOULD
        forbidden_tools=["schedule_payment"],
        guards="mined: PO-less EUR paid instead of escalating (trace t-2208).",
    )
    assert case.origin is Origin.MINED
    assert case.source_trace_id == "t-2208"
    # The authored path is the human's, not the trace's record of the bug.
    assert case.expected_tools != trace.tools_called
    assert "schedule_payment" in case.forbidden_tools
    # And it lands in dev — not golden — until reviewed.
    with pytest.raises(PrematurePromotionError):
        assert_golden_eligible(case)
