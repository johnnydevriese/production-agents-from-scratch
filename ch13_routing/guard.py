"""The re-routing guard: bounded hops, specialist disown, escalate-don't-default.

A routing decision is a bet. The guard hedges it by letting a specialist *disown* a
request it shouldn't own (`handled=False`) and re-routing. Two rules keep that loop
safe, and both are the kind of thing you only learn by getting burned:

1. `max_hops` bounds the loop — a loop over a stateless classifier can ping-pong
   forever (Reporting disowns to AP, AP disowns back), so we cap hops and track
   what we've `tried`.
2. Exhaustion *escalates* (raises `RouteExhausted`); it does NOT fall back to a
   default specialist. A default route is where ambiguous, high-stakes requests go
   to be answered fluently and wrongly — exactly the bug Chapter 13 opens with.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from autopilot import RouteDecision, Router, Specialist


class SpecialistReply(BaseModel):
    handled: bool  # False = "this isn't mine, re-route"
    answer: str | None = None
    suggested_route: Specialist | None = None


class SpecialistHandler(Protocol):
    def handle(self, request: str) -> SpecialistReply: ...


class RouteExhausted(Exception):
    """No specialist owned the request within the hop budget. The caller escalates
    to a human — it must NOT answer with a default specialist."""

    def __init__(self, request: str, tried: set[Specialist]) -> None:
        ordered = sorted(t.value for t in tried)
        super().__init__(f"no specialist owned {request!r}; tried {ordered}")
        self.request = request
        self.tried = frozenset(tried)


def dispatch(
    request: str,
    *,
    router: Router,
    specialists: dict[Specialist, SpecialistHandler],
    max_hops: int = 2,
) -> SpecialistReply:
    """Route, then let the chosen specialist own or disown the request — re-routing a
    bounded number of times, escalating if no one owns it."""
    tried: set[Specialist] = set()
    decision = router.route(request)
    for _ in range(max_hops + 1):
        target = decision.specialist
        if target in tried:  # already refused here — stop, don't ping-pong
            raise RouteExhausted(request, tried)
        tried.add(target)
        reply = specialists[target].handle(request)
        if reply.handled:
            return reply  # the specialist owned it
        if reply.suggested_route is not None and reply.suggested_route not in tried:
            decision = RouteDecision(
                specialist=reply.suggested_route,
                confidence=0.5,
                rationale="re-route on disown",
            )
        else:
            decision = router.route(request)  # ask the router for a second opinion
    raise RouteExhausted(request, tried)  # exhausted: escalate, never silently default
