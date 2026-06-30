"""Offline tests for score-definition registration. Pure + DI — no network.

These pin the recorded gotcha: the payload must serialize with snake_case keys
(`true_label`, not `trueLabel`) or the server silently ignores it and the filter
never appears. Registration is idempotent — re-running skips what already exists —
and the POST is injected, so "did the definitions land?" is asserted with a
recorder instead of a live backend.
"""

from __future__ import annotations

from collections.abc import Mapping

from .register_scores import (
    DEFINITIONS,
    definitions_payload,
    definitions_to_create,
    register,
)


def test_payload_uses_snake_case_keys_the_server_indexes() -> None:
    by_name = {d["name"]: d for d in definitions_payload()}
    po_matched = by_name["po_matched"]
    assert po_matched["type"] == "boolean"
    details = po_matched["details"]
    assert isinstance(details, dict)
    # The bug was camelCase here; snake_case is what the running server reads.
    assert "true_label" in details
    assert "trueLabel" not in details


def test_the_incident_score_is_defined() -> None:
    # po_matched must exist as a typed, filterable definition — it's the column
    # the incident query (`paid = 1 AND po_matched = 0`) filters on.
    assert any(d.name == "po_matched" and d.type == "boolean" for d in DEFINITIONS)


def test_registration_skips_definitions_that_already_exist() -> None:
    existing = {"po_matched", "paid"}
    to_create = {d.name for d in definitions_to_create(existing_names=existing)}
    assert to_create == {"tool_called", "handled_by"}


def test_register_posts_only_the_missing_definitions() -> None:
    posted: list[Mapping[str, object]] = []

    created = register(existing_names={"paid"}, post=posted.append)

    assert "paid" not in created  # already there → not re-posted
    assert {p["name"] for p in posted} == set(created)
    assert "po_matched" in created  # the incident column gets created


def test_register_is_a_noop_when_everything_exists() -> None:
    posted: list[Mapping[str, object]] = []
    all_names = {d.name for d in DEFINITIONS}

    created = register(existing_names=all_names, post=posted.append)

    assert created == []
    assert posted == []
