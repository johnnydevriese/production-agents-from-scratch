"""The economics, on one function — volume is the entire justification.

Distillation pays only above a break-even volume. Below it, serving a small model
(a fixed GPU/endpoint bill) costs more than the frontier calls it saves, and the
frontier API call is the correct engineering decision no matter how elegant the
cascade. This module makes that break-even a number you compute, not a vibe.

The prices are inputs; the *ordering* is the lesson (Appendix A keeps figures
current). Pure arithmetic; no model, no spend.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field


class CostModel(BaseModel):
    """The three numbers that decide whether the cascade beats frontier-only."""

    frontier_cost_per_call: float = Field(gt=0)  # $ per GL-coding call to the teacher
    student_monthly_serving_cost: float = Field(ge=0)  # fixed $/mo for the endpoint
    fallup_rate: float = Field(
        ge=0.0, le=1.0
    )  # fraction with conf < tau (Ch 16 cascade)


def monthly_cost_frontier_only(cost: CostModel, *, invoices_per_month: int) -> float:
    """Today: one frontier call per invoice. Scales linearly with volume."""
    return cost.frontier_cost_per_call * invoices_per_month


def monthly_cost_cascade(cost: CostModel, *, invoices_per_month: int) -> float:
    """The cascade: a fixed serving bill plus frontier calls for the fall-up tail."""
    fall_ups = invoices_per_month * cost.fallup_rate
    return cost.student_monthly_serving_cost + cost.frontier_cost_per_call * fall_ups


def break_even_volume(cost: CostModel) -> int:
    """Smallest monthly invoice count at which the cascade is cheaper than today.

    serving + f·c·N <= c·N  →  N >= serving / (c·(1 − f)). Below this number, keep
    the frontier API call. A cascade that never trusts the student (f == 1) saves
    nothing and can never break even.
    """
    if cost.fallup_rate >= 1.0:
        raise ValueError("a cascade that never trusts the student can never break even")
    savings_per_invoice = cost.frontier_cost_per_call * (1.0 - cost.fallup_rate)
    return math.ceil(cost.student_monthly_serving_cost / savings_per_invoice)
