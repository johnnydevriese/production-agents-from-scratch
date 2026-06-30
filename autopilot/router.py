"""The routing contract — the label space and the Router interface.

Introduced in Chapter 13. A `Specialist` is one of a *fixed* set of destinations
(the bounded action space, at the team level). Every router — the LLM router of
Chapter 13, the LoRA router of Chapter 15, the embedding classifier — returns the
same `RouteDecision`, so swapping implementations changes nothing downstream.

The enum *is* the label space for the learned routers: the route is the label.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field


class Specialist(str, Enum):
    """The fixed set of specialist agents a request can be routed to."""

    AP = "ap"                          # pays invoices (the autopilot spine)
    RECONCILIATION = "reconciliation"  # matches statements, resolves discrepancies
    REPORTING = "reporting"            # answers questions, builds reports
    VENDOR_MGMT = "vendor_mgmt"        # onboarding, bank-detail changes


class RouteDecision(BaseModel):
    """Where a request goes, how sure we are, and why — uniform across routers."""

    specialist: Specialist
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class Router(Protocol):
    """Anything that maps an inbound request to a specialist. Frozen interface."""

    def route(self, request: str) -> RouteDecision: ...
