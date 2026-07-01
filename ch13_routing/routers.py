"""Four ways to produce a `RouteDecision`, behind one frozen `Router` interface.

Swapping routers changes NOTHING downstream: each returns the same `RouteDecision`
(label + confidence + rationale) from `autopilot/router.py`. They differ only in
*how* they decide — a substring table, an LLM call, or nearest-centroid in
embedding space. The fourth, a fine-tuned router, is the Chapter 15 endgame; it is
listed in the book but not built here.

The confidence field is load-bearing: the cascade and the re-routing guard read it
to decide whether to trust a route or fall through to a more expensive stage.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from typing import Protocol

from pydantic_ai import Agent

from autopilot import RouteDecision, Specialist

# ── 1. Keyword fast-path — cheap, deterministic, brittle ──────────────────────

# Data-driven, not an if/elif chain. Only the handful of phrases where a MISS is
# catastrophic belong here; everything else is left to a real router.
_FAST_PATH: dict[str, Specialist] = {
    "billed twice": Specialist.AP,
    "duplicate payment": Specialist.AP,
    "paid twice": Specialist.AP,
    "double charged": Specialist.AP,
    "double-charged": Specialist.AP,
    "remit to": Specialist.AP,
}


def fast_path(request: str) -> RouteDecision | None:
    """Substring match for the few phrases a miss can't be afforded on. Returns
    `None` — *no opinion* — for everything else, never a default route. The instant
    this returns a default instead of `None`, you've built the bug at the end of
    Chapter 13."""
    text = request.casefold()
    for phrase, specialist in _FAST_PATH.items():
        if phrase in text:
            return RouteDecision(
                specialist=specialist,
                confidence=1.0,
                rationale=f"fast-path: {phrase!r}",
            )
    return None


# ── 2. LLM router — flexible, expensive, high-variance ────────────────────────

ROUTER_SYSTEM = (
    "You route finance-ops requests to ONE specialist.\n"
    "- ap: a specific invoice, a payment, a charge, being billed, duplicate or "
    "double charges, vendor bank details to pay.\n"
    "- reconciliation: matching transactions, statement vs ledger differences.\n"
    "- reporting: trends, totals, 'how much did we spend', analytics over history.\n"
    "- vendor_mgmt: onboarding a vendor, changing vendor contact info.\n"
    "A duplicate-charge or 'billed twice' complaint is ALWAYS ap, never reporting."
)


class LLMRouter:
    """A PydanticAI agent with structured output. The agent is injected, so a test
    drives it with a `FunctionModel` and spends nothing (Chapter 20)."""

    def __init__(self, *, agent: Agent[None, RouteDecision]) -> None:
        self._agent = agent

    def __repr__(self) -> str:
        return "LLMRouter()"

    def route(self, request: str) -> RouteDecision:
        return self._agent.run_sync(request).output


def build_llm_router(model: str = "anthropic:claude-sonnet-5") -> LLMRouter:
    """Construct the shipped LLM router. The carve-out that fixes the production
    misroute lives in the system prompt — prompt-as-code (Chapter 8)."""
    return LLMRouter(
        agent=Agent(model, output_type=RouteDecision, system_prompt=ROUTER_SYSTEM)
    )


# ── 3. Embedding classifier — fast, learns from examples, opaque ──────────────


class Embedder(Protocol):
    """Maps text to a vector. A real one calls an embeddings endpoint; a test passes
    a deterministic stand-in so the classifier is exercised offline."""

    def __call__(self, text: str) -> Sequence[float]: ...


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if norm == 0.0:
        raise ValueError("cannot rank a zero-length embedding")
    return dot / norm


def _mean_by_label(
    embed: Embedder, labeled: Sequence[tuple[str, Specialist]]
) -> dict[Specialist, list[float]]:
    grouped: dict[Specialist, list[Sequence[float]]] = defaultdict(list)
    for text, label in labeled:
        grouped[label].append(embed(text))
    return {
        label: [sum(col) / len(vecs) for col in zip(*vecs, strict=True)]
        for label, vecs in grouped.items()
    }


class EmbeddingRouter:
    """Route to the nearest class centroid in embedding space. Deterministic given a
    fixed embedding model, and learns from labeled examples rather than rules."""

    def __init__(
        self, *, embed: Embedder, labeled: Sequence[tuple[str, Specialist]]
    ) -> None:
        self._embed = embed
        self._centroids = _mean_by_label(embed, labeled)

    def __repr__(self) -> str:
        return f"EmbeddingRouter(labels={sorted(c.value for c in self._centroids)})"

    def route(self, request: str) -> RouteDecision:
        vector = self._embed(request)
        ranked = sorted(
            ((label, _cosine(vector, c)) for label, c in self._centroids.items()),
            key=lambda pair: pair[1],
            reverse=True,
        )
        (top_label, top_score), (_, second_score) = ranked[0], ranked[1]
        margin = top_score - second_score
        return RouteDecision(
            specialist=top_label,
            # The margin between the top two labels IS the confidence; clamp it into
            # RouteDecision's [0, 1] (cosine margins can exceed 1).
            confidence=max(0.0, min(1.0, margin)),
            rationale=f"nearest={top_label.value} margin={margin:.2f}",
        )
