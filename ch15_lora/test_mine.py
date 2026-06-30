"""Stage 1 — the label comes from a human, and the hygiene is the real work.

These pin the chapter's central data discipline: never label from the model's own
output; collapse the power-law duplicates; surface the rare class the aggregate
hides; and hold out by *time*, not at random. Pure functions, no spend.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from autopilot import Specialist

from .mine import (
    RouteSource,
    RoutingSignal,
    class_balance,
    majority_baseline,
    mine_confirmed_routes,
    time_split,
)

_NOW = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)


def _signal(
    request: str,
    landed_on: Specialist,
    *,
    human_confirmed: bool,
    trace_id: str = "tr-1",
    occurred_at: datetime = _NOW,
) -> RoutingSignal:
    return RoutingSignal(
        request=request,
        landed_on=landed_on,
        human_confirmed=human_confirmed,
        source=RouteSource.ESCALATION,
        trace_id=trace_id,
        occurred_at=occurred_at,
    )


def test_only_human_confirmed_signals_become_labels() -> None:
    signals = [
        _signal("where is invoice INV-1043", Specialist.AP, human_confirmed=True),
        # The LLM router decided this one and no human verified it — NOT a label.
        _signal(
            "how much did we spend in Q2", Specialist.REPORTING, human_confirmed=False
        ),
    ]
    examples = mine_confirmed_routes(signals)
    assert [example.route for example in examples] == [Specialist.AP]
    assert all(example.request != "how much did we spend in Q2" for example in examples)


def test_a_power_law_template_is_deduped_to_one_example() -> None:
    # The same template arrives 500 times; left in, it would dominate the loss.
    signals = [
        _signal("where is my invoice", Specialist.AP, human_confirmed=True)
        for _ in range(500)
    ]
    examples = mine_confirmed_routes(signals)
    assert len(examples) == 1


def test_the_majority_baseline_is_the_do_nothing_floor() -> None:
    # 97 AP, 3 VENDOR_MGMT: a model that never predicts the rare class scores 0.97.
    examples = mine_confirmed_routes(
        [
            _signal(
                f"pay invoice {i}",
                Specialist.AP,
                human_confirmed=True,
                trace_id=f"ap-{i}",
            )
            for i in range(97)
        ]
        + [
            _signal(
                f"onboard vendor {i}",
                Specialist.VENDOR_MGMT,
                human_confirmed=True,
                trace_id=f"vm-{i}",
            )
            for i in range(3)
        ]
    )
    balance = class_balance(examples)
    assert balance[Specialist.AP] == 97
    assert balance[Specialist.VENDOR_MGMT] == 3
    assert majority_baseline(examples) == pytest.approx(0.97)


def test_time_split_never_leaks_the_future_into_training() -> None:
    cutoff = _NOW
    older = [
        _signal(
            f"older {i}",
            Specialist.AP,
            human_confirmed=True,
            trace_id=f"o-{i}",
            occurred_at=_NOW - timedelta(days=i + 1),
        )
        for i in range(5)
    ]
    newer = [
        _signal(
            f"newer {i}",
            Specialist.REPORTING,
            human_confirmed=True,
            trace_id=f"n-{i}",
            occurred_at=_NOW + timedelta(days=i),
        )
        for i in range(4)
    ]
    examples = mine_confirmed_routes(older + newer)
    train, test = time_split(examples, cutoff=cutoff)

    assert len(train) == 5
    assert len(test) == 4
    assert all(example.occurred_at < cutoff for example in train)
    assert all(example.occurred_at >= cutoff for example in test)


def test_a_baseline_over_no_examples_raises() -> None:
    with pytest.raises(ValueError, match="zero examples"):
        majority_baseline([])
