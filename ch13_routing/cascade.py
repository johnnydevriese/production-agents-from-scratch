"""The cascade: fast-path → embedding → LLM, cheapest first, abstain-don't-guess.

Each stage either decides or *abstains* — the fast-path returns `None`, the
embedding router returns a low-confidence margin — and abstention, not a guessed
default, is what passes control to the next, more expensive stage. The fast-path
catches the few phrases a miss can't be afforded on; the embedding router handles
the bulk once labels exist; the LLM router is the expensive fallback for the
genuinely ambiguous tail.
"""

from __future__ import annotations

from autopilot import RouteDecision, Router

from .routers import EmbeddingRouter, fast_path


class CascadeRouter:
    """A `Router` composed of cheaper routers. Conforms to the same interface, so it
    drops in wherever a single router did."""

    def __init__(
        self,
        *,
        embedding: EmbeddingRouter,
        llm: Router,
        margin_threshold: float = 0.1,
    ) -> None:
        self._embedding = embedding
        self._llm = llm
        self._margin_threshold = margin_threshold

    def __repr__(self) -> str:
        return f"CascadeRouter(margin_threshold={self._margin_threshold})"

    def route(self, request: str) -> RouteDecision:
        hit = fast_path(request)
        if hit is not None:
            return hit  # a phrase we can't afford to miss — decided in microseconds
        embedded = self._embedding.route(request)
        if embedded.confidence >= self._margin_threshold:
            return embedded  # confident enough; no model call
        return self._llm.route(request)  # ambiguous tail → expensive fallback
