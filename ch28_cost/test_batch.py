"""Batch vs on-demand — pure cost math and the risk-keyed batchability rule.

These pin the ~50% async discount on the overnight job and the chapter's rule for
*which* steps can take it: read-heavy/decision-light steps batch; money-movement,
irreversible writes, and external comms do not. Batch the thinking, not the wire
transfer.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from .batch import estimate_batch_savings, is_batchable


def test_the_overnight_job_is_about_half_price_as_a_batch() -> None:
    est = estimate_batch_savings(n_invoices=40_000, per_invoice_cost=Decimal("0.05"))
    assert est.on_demand == Decimal("2000.00")
    assert est.batch == Decimal("1000.000")
    assert est.saved == est.on_demand - est.batch


def test_read_heavy_steps_are_batchable() -> None:
    assert is_batchable("extract_invoice")  # the Ch 9 capability
    assert is_batchable("match_to_po")
    assert is_batchable("lookup_invoice")


def test_money_movement_and_writes_are_not_batchable() -> None:
    assert not is_batchable("schedule_payment")  # the wire transfer
    assert not is_batchable("post_journal_entry")  # irreversible write
    assert not is_batchable("request_approval")  # external comms


def test_an_unknown_step_raises() -> None:
    with pytest.raises(KeyError):
        is_batchable("teleport_funds")
