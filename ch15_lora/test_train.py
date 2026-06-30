"""Stage 2 — the corpus reuses the router's prompt, and the run is reproducible.

These pin two claims the chapter leans on: the training prompt is the LLM router's
*exact* system prompt (so the head-to-head is fair and the LLM router stays a
drop-in fallback), and the training run's identity is a pure function of its
inputs — same data + same config → same fingerprint, edit a label and it changes.
Offline, no GPU, no spend.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from autopilot import Specialist
from ch13_routing.routers import ROUTER_SYSTEM

from .mine import RouteSource, RoutingExample
from .train import LoraSettings, build_training_corpus, corpus_fingerprint, to_chat

_NOW = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)


def _example(request: str, route: Specialist) -> RoutingExample:
    return RoutingExample(
        request=request,
        route=route,
        source=RouteSource.DISOWN,
        trace_id="tr-1",
        occurred_at=_NOW,
    )


def _settings() -> LoraSettings:
    return LoraSettings(base_model="an-open-instruct-model-1to8b")


def test_a_training_row_reuses_the_llm_routers_exact_prompt() -> None:
    chat = to_chat(_example("where is invoice INV-1043", Specialist.AP))
    system, user, assistant = chat.messages

    assert system.role == "system"
    assert system.content == ROUTER_SYSTEM  # the SAME prompt, verbatim
    assert user.role == "user"
    assert user.content == "where is invoice INV-1043"
    assert assistant.role == "assistant"
    assert assistant.content == Specialist.AP.value == "ap"  # the label token out


def test_the_fingerprint_is_deterministic_for_the_same_inputs() -> None:
    examples = [
        _example("pay it", Specialist.AP),
        _example("report it", Specialist.REPORTING),
    ]
    settings = _settings()
    assert corpus_fingerprint(examples, settings) == corpus_fingerprint(
        examples, settings
    )


def test_editing_a_single_label_changes_the_fingerprint() -> None:
    settings = _settings()
    before = [_example("pay it", Specialist.AP)]
    after = [
        _example("pay it", Specialist.RECONCILIATION)
    ]  # a human corrected the label
    assert corpus_fingerprint(before, settings) != corpus_fingerprint(after, settings)


def test_changing_the_seed_changes_the_fingerprint() -> None:
    examples = [_example("pay it", Specialist.AP)]
    assert corpus_fingerprint(
        examples, LoraSettings(base_model="m", seed=0)
    ) != corpus_fingerprint(examples, LoraSettings(base_model="m", seed=1))


def test_lora_settings_are_a_frozen_artifact() -> None:
    settings = _settings()
    with pytest.raises(ValidationError):
        settings.r = 8  # type: ignore[misc]  # frozen: the config that trained an adapter cannot drift


def test_the_corpus_is_one_chat_row_per_example() -> None:
    examples = [
        _example("pay it", Specialist.AP),
        _example("report it", Specialist.REPORTING),
    ]
    corpus = build_training_corpus(examples)
    assert len(corpus) == 2
    assert [row.messages[-1].content for row in corpus] == ["ap", "reporting"]
