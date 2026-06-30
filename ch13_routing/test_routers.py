"""ch13 — the four routers, three of them tested with no model at all.

The fast-path and the embedding classifier are pure code: deterministic, offline,
free. The LLM router is the one that costs money in production, so its test injects
a `FunctionModel` — same zero-spend discipline as every other framework checkpoint.
"""

from __future__ import annotations

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from autopilot import RouteDecision, Specialist

from .routers import EmbeddingRouter, LLMRouter, fast_path
from .sample_routing import LABELED_EXAMPLES, keyword_embed


@pytest.mark.parametrize(
    "request_text",
    ["Why was I billed twice for #1043?", "I think this was a DUPLICATE PAYMENT"],
)
def test_fast_path_catches_high_stakes_phrases(request_text: str) -> None:
    decision = fast_path(request_text)
    assert decision is not None
    assert decision.specialist is Specialist.AP
    assert decision.confidence == 1.0


def test_fast_path_abstains_instead_of_defaulting() -> None:
    # A phrasing the table doesn't list: no opinion (None), NOT a default route.
    assert fast_path("you double-debited my account last week") is None
    assert fast_path("how much did we spend on travel?") is None


def test_embedding_router_picks_the_nearest_centroid() -> None:
    router = EmbeddingRouter(embed=keyword_embed, labeled=LABELED_EXAMPLES)
    assert router.route("pay this invoice now").specialist is Specialist.AP
    assert router.route("reconcile the ledger").specialist is Specialist.RECONCILIATION
    assert router.route("spend report please").specialist is Specialist.REPORTING


def test_embedding_router_reports_low_confidence_when_ambiguous() -> None:
    router = EmbeddingRouter(embed=keyword_embed, labeled=LABELED_EXAMPLES)
    # Lights both the AP ("charge") and REPORTING ("trend") axes → near-tied margin.
    ambiguous = router.route("what's the trend on this charge")
    clear = router.route("pay invoice 1043")
    assert ambiguous.confidence < clear.confidence
    assert ambiguous.confidence < 0.1  # below a sane cascade threshold → fall through


def _llm_emitting(decision: RouteDecision) -> FunctionModel:
    def model_fn(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        out = (info.output_tools or [])[0].name
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=out,
                    args={
                        "specialist": decision.specialist.value,
                        "confidence": decision.confidence,
                        "rationale": decision.rationale,
                    },
                )
            ]
        )

    return FunctionModel(model_fn)


def test_llm_router_returns_a_route_decision() -> None:
    agent: Agent[None, RouteDecision] = Agent(
        "anthropic:claude-sonnet-4-6", output_type=RouteDecision
    )
    router = LLMRouter(agent=agent)
    scripted = RouteDecision(
        specialist=Specialist.AP, confidence=0.9, rationale="billed twice → ap"
    )
    with agent.override(model=_llm_emitting(scripted)):
        decision = router.route("why was I billed twice?")
    assert decision.specialist is Specialist.AP
    assert decision.confidence == pytest.approx(0.9)
