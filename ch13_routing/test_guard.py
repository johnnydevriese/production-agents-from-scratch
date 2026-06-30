"""ch13 — the re-routing guard: own, disown-and-reroute, and the no-default rule.

The load-bearing test is `test_exhaustion_escalates_it_does_not_default`: when no
specialist owns a request, the guard raises instead of dumping it on a default
agent. That single behavior is the difference between a misroute that lands in an
escalation queue (a near-miss you learn from) and one that gets a fluent, wrong
answer.
"""

from __future__ import annotations

import pytest

from autopilot import RouteDecision, Specialist

from .guard import (
    RouteExhausted,
    SpecialistHandler,
    SpecialistReply,
    dispatch,
)


class _FixedRouter:
    def __init__(self, specialist: Specialist) -> None:
        self._specialist = specialist

    def route(self, request: str) -> RouteDecision:
        return RouteDecision(
            specialist=self._specialist, confidence=0.7, rationale="fixed"
        )


class _StubHandler:
    def __init__(self, reply: SpecialistReply) -> None:
        self._reply = reply
        self.calls = 0

    def handle(self, request: str) -> SpecialistReply:
        self.calls += 1
        return self._reply


def test_a_specialist_that_owns_it_short_circuits() -> None:
    ap = _StubHandler(SpecialistReply(handled=True, answer="paid"))
    specialists: dict[Specialist, SpecialistHandler] = {Specialist.AP: ap}
    reply = dispatch(
        "pay invoice 1043", router=_FixedRouter(Specialist.AP), specialists=specialists
    )
    assert reply.answer == "paid"
    assert ap.calls == 1  # owned on the first hop, no re-route


def test_disown_reroutes_to_the_suggested_specialist() -> None:
    reporting = _StubHandler(
        SpecialistReply(handled=False, suggested_route=Specialist.AP)
    )
    ap = _StubHandler(SpecialistReply(handled=True, answer="found the duplicate"))
    specialists: dict[Specialist, SpecialistHandler] = {
        Specialist.REPORTING: reporting,
        Specialist.AP: ap,
    }
    reply = dispatch(
        "why was I billed twice?",
        router=_FixedRouter(Specialist.REPORTING),
        specialists=specialists,
    )
    assert reply.answer == "found the duplicate"  # AP, not the misrouted Reporting
    assert reporting.calls == 1
    assert ap.calls == 1


def test_exhaustion_escalates_it_does_not_default() -> None:
    # Every specialist disowns and suggests nothing → the guard must RAISE, not pick
    # a default. This is the chapter's central failure, prevented.
    disowner = _StubHandler(SpecialistReply(handled=False))
    specialists: dict[Specialist, SpecialistHandler] = {
        Specialist.REPORTING: disowner,
        Specialist.AP: disowner,
    }
    with pytest.raises(RouteExhausted) as caught:
        dispatch(
            "something genuinely ambiguous",
            router=_FixedRouter(Specialist.REPORTING),
            specialists=specialists,
        )
    assert Specialist.REPORTING in caught.value.tried


def test_pingpong_is_bounded_and_escalates() -> None:
    # Reporting → AP → Reporting → … a stateless loop that would run forever.
    reporting = _StubHandler(
        SpecialistReply(handled=False, suggested_route=Specialist.AP)
    )
    ap = _StubHandler(
        SpecialistReply(handled=False, suggested_route=Specialist.REPORTING)
    )
    specialists: dict[Specialist, SpecialistHandler] = {
        Specialist.REPORTING: reporting,
        Specialist.AP: ap,
    }
    with pytest.raises(RouteExhausted):
        dispatch(
            "ambiguous and contested",
            router=_FixedRouter(Specialist.REPORTING),
            specialists=specialists,
        )
    # `tried` stops re-sending: each handler ran at most once, no infinite loop.
    assert reporting.calls == 1
    assert ap.calls == 1
