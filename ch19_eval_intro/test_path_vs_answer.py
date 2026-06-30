"""The asymmetry that defines Part VII: one run, answer-check green, path-check red."""

from __future__ import annotations

import pytest

from ch19_eval_intro.checks import answer_cites_invoice, payment_matches_lookup
from ch19_eval_intro.run import GOOD_RUN, RUN_4471, AgentRun


def test_fluent_answer_passes_the_naive_answer_check() -> None:
    result = answer_cites_invoice(RUN_4471, invoice_number="#1043", amount="$2,988.09")
    assert result.passed


def test_path_check_catches_the_wrong_vendor() -> None:
    result = payment_matches_lookup(RUN_4471)
    assert not result.passed
    assert "V-ACME" in result.detail
    assert "V-ACMI" in result.detail


def test_the_same_answer_check_is_green_on_both_runs() -> None:
    # The answer is byte-for-byte identical on the broken and the correct run — which
    # is the whole point: the answer cannot tell them apart, only the path can.
    assert RUN_4471.answer == GOOD_RUN.answer
    for run in (RUN_4471, GOOD_RUN):
        assert answer_cites_invoice(
            run, invoice_number="#1043", amount="$2,988.09"
        ).passed


def test_path_check_passes_only_on_the_correct_run() -> None:
    assert payment_matches_lookup(GOOD_RUN).passed
    assert not payment_matches_lookup(RUN_4471).passed


def test_path_check_fails_loud_when_a_required_tool_is_absent() -> None:
    truncated = AgentRun(run_id="x", path=RUN_4471.path[:1], answer="")
    with pytest.raises(LookupError):
        payment_matches_lookup(truncated)
