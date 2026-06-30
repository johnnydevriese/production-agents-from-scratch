"""Read the bill off the trace — pure summation over per-span usage.

These pin the chapter's diagnosis: input dominates output (so optimize input), and
the fixed preamble re-sent on every loop turn is a quantifiable tax — the exact
quantity prompt caching converts into cheap reads.
"""

from __future__ import annotations

from .bill import preamble_tax, summarize_invoice
from .pricing import ModelPricing, Usage

_MID = ModelPricing.standard("mid", input_per_1k="0.003", output_per_1k="0.015")

# The per-invoice budget shape from the chapter: ~14,700 in, ~830 out across the loop.
_CLEAN_INVOICE = [
    Usage(input_tokens=2000, output_tokens=260),
    Usage(input_tokens=2300, output_tokens=40),
    Usage(input_tokens=2400, output_tokens=120),
    Usage(input_tokens=2500, output_tokens=90),
    Usage(input_tokens=2700, output_tokens=180),
    Usage(input_tokens=2800, output_tokens=140),
]


def test_summarize_folds_the_loop_into_one_line_item() -> None:
    bill = summarize_invoice(_CLEAN_INVOICE, pricing=_MID)
    assert bill.calls == 6
    assert bill.total_input_tokens == 14_700
    assert bill.total_output_tokens == 830


def test_input_dominates_output() -> None:
    bill = summarize_invoice(_CLEAN_INVOICE, pricing=_MID)
    assert bill.input_output_ratio > 15  # the lopsided ~18:1 the chapter calls out


def test_preamble_tax_is_what_you_pay_to_re_send_the_prefix() -> None:
    # Six turns, a 1,400-token preamble: you send it once and re-send it five times.
    assert preamble_tax(preamble_tokens=1400, loop_turns=6) == 1400 * 5


def test_a_single_turn_pays_no_preamble_tax() -> None:
    assert preamble_tax(preamble_tokens=1400, loop_turns=1) == 0
    assert preamble_tax(preamble_tokens=1400, loop_turns=0) == 0
