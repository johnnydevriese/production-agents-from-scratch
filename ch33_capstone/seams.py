"""The seams — composition bugs that live *between* correct boxes.

The clean diagram lies. Each discipline passed its own test; the system can still
fail the test no one wrote, because the bug is in the wiring between two right
parts. The four seams below are where assembly actually breaks, each one a place
two correct disciplines were joined wrong — and each one a chapter to re-read.

The agent→workflow seam is the dangerous one, so we don't just describe it — we
*execute* it. Wiring `schedule_payment` straight to the rail (the hot-fix that
skips the durable workflow that mints the idempotency key) double-pays on the
first retry; routing through the keyed path pays exactly once. We reuse Chapter
30's offline reproduction on Chapter 26's real rail — composition all the way
down. Zero spend.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from autopilot import InvoiceId
from autopilot.fixtures import INVOICES
from ch26_durable.rail import IdempotentRail
from ch30_case_study.reproduce import replay_payment

_INVOICE = INVOICES[InvoiceId("INV-1043")]


class Boundary(str, Enum):
    """The four wiring boundaries where composition bugs hide."""

    ROUTER_TO_AGENT = "router→agent"
    AGENT_TO_WORKFLOW = "agent→workflow"
    PROMPT_TO_GUARDRAIL = "prompt→guardrail"
    EVAL_TO_REALITY = "eval→reality"


class Seam(BaseModel, frozen=True):
    """One seam: the composition bug, and the discipline that catches it."""

    boundary: Boundary
    bug: str
    caught_by: str  # the eval/assertion that fires
    chapter: str


# The chapter's seam table, as data. Each row is a real failure mode; the
# `caught_by` column is the thing that turns "passed in isolation" into "caught".
SEAMS: tuple[Seam, ...] = (
    Seam(
        boundary=Boundary.ROUTER_TO_AGENT,
        bug="trace context not propagated across the handoff; span tree breaks",
        caught_by="span-parenting assertions",
        chapter="Ch 17",
    ),
    Seam(
        boundary=Boundary.AGENT_TO_WORKFLOW,
        bug="schedule_payment wired to the rail directly, bypassing the durable "
        "workflow that mints the key; double-pays on the first crash",
        caught_by="idempotency structural eval",
        chapter="Ch 20",
    ),
    Seam(
        boundary=Boundary.PROMPT_TO_GUARDRAIL,
        bug="a matching-quality prompt edit widens the auto-pay trigger; the "
        "injection suite was never re-run against the new prompt",
        caught_by="guardrail regression in the offline gate",
        chapter="Ch 10",
    ),
    Seam(
        boundary=Boundary.EVAL_TO_REALITY,
        bug="offline suite is green but tests the old route; production sees a "
        "phrasing the router now misclassifies",
        caught_by="online monitor + corrections fed back as new cases",
        chapter="Ch 23",
    ),
)


def direct_rail_transfers() -> int:
    """The agent→workflow seam, broken: `schedule_payment` calls the rail directly,
    so a retry mints a fresh key and money moves twice. Returns the transfer count."""
    rail = IdempotentRail()
    replay_payment(invoice=_INVOICE, rail=rail, thread_key=False, attempts=2)
    return rail.transfer_count


def durable_workflow_transfers() -> int:
    """The seam, wired right: the durable path threads a deterministic key, so the
    same retry dedupes and money moves once. Returns the transfer count."""
    rail = IdempotentRail()
    replay_payment(invoice=_INVOICE, rail=rail, thread_key=True, attempts=2)
    return rail.transfer_count
