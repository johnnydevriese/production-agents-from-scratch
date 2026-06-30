"""The seams — composition bugs between correct boxes.

These pin: the seam catalog covers all four wiring boundaries; and the dangerous
one (agent→workflow) is *executed*, not just described — wiring schedule_payment
straight to the rail double-pays, while routing through the durable keyed path pays
once. Reuses Ch 30's reproduction on Ch 26's real rail; pure, no spend.
"""

from __future__ import annotations

from .seams import (
    SEAMS,
    Boundary,
    direct_rail_transfers,
    durable_workflow_transfers,
)


def test_the_catalog_covers_every_wiring_boundary() -> None:
    assert {seam.boundary for seam in SEAMS} == set(Boundary)


def test_every_seam_names_what_catches_it() -> None:
    # A seam without a catching discipline is just a complaint.
    assert all(seam.caught_by and seam.chapter for seam in SEAMS)


def test_the_direct_rail_hotfix_double_pays() -> None:
    # The seam, broken: schedule_payment bypasses the durable workflow's key.
    assert direct_rail_transfers() == 2


def test_the_durable_workflow_pays_exactly_once() -> None:
    # The seam, wired right: the deterministic key dedupes the retry.
    assert durable_workflow_transfers() == 1


def test_the_idempotency_seam_is_the_money_path_one() -> None:
    seam = next(s for s in SEAMS if s.boundary is Boundary.AGENT_TO_WORKFLOW)
    assert "double-pay" in seam.bug
    assert seam.chapter == "Ch 20"  # the idempotency structural eval catches it
