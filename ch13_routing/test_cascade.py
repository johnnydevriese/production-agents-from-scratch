"""ch13 — the cascade decides at the cheapest stage that's confident enough.

Cheap-to-expensive with abstention between stages: the fast-path wins outright on a
known phrase; the embedding router decides the confident bulk; only the ambiguous
tail reaches the LLM. We prove the ordering by injecting an LLM router that *raises
if called* — so a passing test is proof the expensive stage was never reached.
"""

from __future__ import annotations

from autopilot import RouteDecision, Specialist

from .cascade import CascadeRouter
from .routers import EmbeddingRouter
from .sample_routing import LABELED_EXAMPLES, keyword_embed


class _ExplodingRouter:
    """An LLM-router stand-in that fails if the cascade ever falls through to it."""

    def route(self, request: str) -> RouteDecision:
        raise AssertionError(f"LLM router should not have been called for {request!r}")


class _FixedRouter:
    def __init__(self, decision: RouteDecision) -> None:
        self._decision = decision

    def route(self, request: str) -> RouteDecision:
        return self._decision


def _embedding() -> EmbeddingRouter:
    return EmbeddingRouter(embed=keyword_embed, labeled=LABELED_EXAMPLES)


def test_fast_path_short_circuits_before_any_model() -> None:
    cascade = CascadeRouter(embedding=_embedding(), llm=_ExplodingRouter())
    decision = cascade.route("why was I billed twice for #1043?")
    assert decision.specialist is Specialist.AP
    assert decision.rationale.startswith("fast-path:")  # decided at stage 1


def test_embedding_decides_the_confident_bulk() -> None:
    cascade = CascadeRouter(embedding=_embedding(), llm=_ExplodingRouter())
    decision = cascade.route("reconcile the ledger statement")
    assert decision.specialist is Specialist.RECONCILIATION
    assert decision.rationale.startswith("nearest=")  # decided at stage 2, no LLM


def test_ambiguous_request_falls_through_to_the_llm() -> None:
    fallback = RouteDecision(
        specialist=Specialist.AP, confidence=0.8, rationale="llm: charge → ap"
    )
    cascade = CascadeRouter(embedding=_embedding(), llm=_FixedRouter(fallback))
    decision = cascade.route("what's the trend on this charge")  # two axes lit
    assert decision is fallback  # the expensive stage broke the tie
