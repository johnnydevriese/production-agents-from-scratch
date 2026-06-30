"""Stage 3 — serve the adapter behind the frozen `Router` Protocol.

The LoRA router satisfies the same `Router` interface as every router in Chapter
13, so it drops into the cascade and the re-routing guard unchanged. Two
properties the LLM router couldn't give you for free:

- the label set is enforced by *constrained decoding* — the model emits one of the
  four `Specialist` values or nothing; it cannot hallucinate a fifth route or
  return prose, so the structured-output retry of Chapter 9 is unnecessary;
- the confidence is the adapter's returned score over the labels — more grounded
  than a self-reported LLM number, but still something Chapter 16 calibrates before
  a threshold should trust it.

The forward pass is behind an injected `InferenceClient` Protocol; tests pass a
deterministic fake and spend nothing. README.md documents the real local inference
client (vLLM / transformers) that loads the adapter on the frozen base.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, Field

from autopilot import RouteDecision, Specialist
from ch13_routing.routers import ROUTER_SYSTEM

ALLOWED_LABELS: tuple[str, ...] = tuple(specialist.value for specialist in Specialist)


class ClassifyResult(BaseModel):
    """A constrained-decoding result: a label from the allowed set and its prob."""

    label: str
    prob: float = Field(ge=0.0, le=1.0)


class InferenceClient(Protocol):
    """One small, local forward pass that emits a label from `allowed` and its prob.

    A real implementation loads the LoRA adapter on the frozen base and decodes
    with the label set as a hard constraint; a test passes a deterministic
    stand-in (Ch 20) so the router is exercised offline.
    """

    def classify(
        self, *, system: str, user: str, allowed: Sequence[str]
    ) -> ClassifyResult: ...


class LoRARouter:
    """The learned router. Satisfies the Chapter 13 `Router` Protocol exactly."""

    def __init__(self, *, client: InferenceClient) -> None:
        self._client = client

    def __repr__(self) -> str:
        return "LoRARouter()"

    def route(self, request: str) -> RouteDecision:
        result = self._client.classify(
            system=ROUTER_SYSTEM, user=request, allowed=ALLOWED_LABELS
        )
        # Constrained decoding should make this total; we still fail closed — an
        # off-menu label raises rather than silently inventing a route.
        specialist = Specialist(result.label)
        return RouteDecision(
            specialist=specialist,
            confidence=result.prob,  # adapter score for the winning label
            rationale=f"lora:{specialist.value} p={result.prob:.2f}",
        )
