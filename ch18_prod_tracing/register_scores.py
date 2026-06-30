"""Register the feedback-score *definitions* so the UI offers them as filters.

A score you write but never define is data the backend can't index — you've built
an unsearchable column and won't find out until the incident. So the definitions
are registered once, idempotently (skip any that already exist), with their type
and labels.

The recorded gotcha (honest, from the real reference app): an SDK-generated client
serialized these with the wrong key casing for the running server, so registration
silently no-op'd and the filter never appeared. The fix — and the test below —
is to POST the raw payload with **snake_case** keys (`true_label`, not
`trueLabel`). The lesson outlives the bug: verify your scores actually land.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Literal

from pydantic import BaseModel, Field

ScoreType = Literal["boolean", "categorical", "numerical"]


class ScoreDefinition(BaseModel):
    name: str
    type: ScoreType
    details: dict[str, str] = Field(default_factory=dict)


DEFINITIONS: list[ScoreDefinition] = [
    ScoreDefinition(
        name="po_matched",
        type="boolean",
        details={"true_label": "matched", "false_label": "unmatched"},
    ),
    ScoreDefinition(
        name="paid",
        type="boolean",
        details={"true_label": "paid", "false_label": "not paid"},
    ),
    ScoreDefinition(
        name="tool_called",
        type="boolean",
        details={"true_label": "called a tool", "false_label": "answered cold"},
    ),
    ScoreDefinition(
        name="handled_by",
        type="categorical",
        details={"ap": "accounts payable", "recon": "reconciliation"},
    ),
]


def definitions_payload() -> list[dict[str, object]]:
    """The exact JSON to POST — snake_case keys, the casing the server indexes."""
    return [d.model_dump() for d in DEFINITIONS]


def definitions_to_create(*, existing_names: set[str]) -> list[ScoreDefinition]:
    """Idempotent: only the definitions the server doesn't already have."""
    return [d for d in DEFINITIONS if d.name not in existing_names]


def register(
    *,
    existing_names: set[str],
    post: Callable[[Mapping[str, object]], None],
) -> list[str]:
    """POST each missing definition via the injected `post`; return what we created.

    `post` is injected (DI): a real run wires it to an `httpx` client aimed at the
    backend's `/feedback-definitions`; the tests pass a recorder, so this is
    exercised with no network. Returns the names created, so a caller can log and
    *verify they landed*.
    """
    created: list[str] = []
    for definition in definitions_to_create(existing_names=existing_names):
        post(definition.model_dump())
        created.append(definition.name)
    return created
