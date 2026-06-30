"""Stage 2 — prepare the training corpus and pin the adapter's identity.

The actual weight training imports `peft`/`transformers` and needs a GPU; it is
documented in README.md, not run here — the checkpoint is offline and spends
nothing. What this module owns is everything that must be *correct* before a GPU
is provisioned:

- the chat formatting that reuses the LLM router's *exact* system prompt, so the
  adapter's job is identical to the LLM router's and the head-to-head is fair;
- the LoRA hyperparameters as a frozen, versioned artifact;
- a deterministic fingerprint over (corpus, config) that stands in for the
  chapter's reproducibility claim — same data + same seed + same config should
  reproduce under a pinned stack, and this pins the inputs that make that claim
  auditable.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from pydantic import BaseModel, Field

from ch13_routing.routers import ROUTER_SYSTEM  # the SAME prompt the LLM router uses

from .mine import RoutingExample


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatExample(BaseModel):
    """One training row: the routing instruction, the request, the gold label."""

    messages: list[ChatMessage]


def to_chat(example: RoutingExample) -> ChatExample:
    """Frame routing as text generation: prompt in, the label token out.

    The system prompt is the LLM router's, verbatim — so the adapter learns the
    same job against the same instruction and label space, the stage-4 head-to-head
    is a fair fight, and the LLM router stays a drop-in fallback for any input.
    """
    return ChatExample(
        messages=[
            ChatMessage(role="system", content=ROUTER_SYSTEM),
            ChatMessage(role="user", content=example.request),
            ChatMessage(role="assistant", content=example.route.value),
        ]
    )


def build_training_corpus(examples: Sequence[RoutingExample]) -> list[ChatExample]:
    return [to_chat(example) for example in examples]


class LoraSettings(BaseModel, frozen=True):
    """The adapter config from the chapter, as a versioned artifact.

    Training touches only these small matrices; the base model's billions of
    weights stay frozen. `r` is the rank of the low-rank update (Appendix C),
    `lora_alpha` scales it, and `seed` is what makes the run reproducible.
    """

    base_model: str
    r: int = Field(default=16, gt=0)
    lora_alpha: int = Field(default=32, gt=0)
    target_modules: str = "all-linear"
    task_type: str = "CAUSAL_LM"
    seed: int = 0


def corpus_fingerprint(
    examples: Sequence[RoutingExample], settings: LoraSettings
) -> str:
    """A deterministic hash of (corpus, config) — the training run's identity.

    Real LoRA training should reproduce under the same pinned stack; we can't hash
    the weights from here, but we can pin the *inputs* that determine them. Same
    corpus + same settings → same fingerprint; edit one label and it changes.
    That repeatability is a feature you are buying: after Chapter 1 (an LLM call is
    a random variable), a router whose training identity is a pure function of its
    inputs is a genuinely different kind of object.
    """
    corpus = build_training_corpus(examples)
    basis = json.dumps(
        {
            "settings": settings.model_dump(mode="json"),
            "corpus": [example.model_dump(mode="json") for example in corpus],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(basis.encode()).hexdigest()
