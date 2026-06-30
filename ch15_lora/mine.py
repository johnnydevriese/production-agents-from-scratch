"""Stage 1 — mine production traces into human-confirmed routing labels.

The chapter's claim: your best routing dataset is already in your database, and
the only labels worth training on are the ones a *human* confirmed on a real
input. This module is the hygiene that turns raw captured signals (Ch 23) into a
clean, balanced, time-split training set — and the reason a confidently-broken
adapter is almost always a data bug, not a modeling one.

Everything here is a pure function over recorded signals: no model, no GPU, no
spend. The actual training that consumes these examples lives in `train.py` (and,
for real, in README.md).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from autopilot import Specialist


class RouteSource(str, Enum):
    """Where a confirmed label came from — kept for auditing the training set."""

    DISOWN = "disown"  # Ch 13 re-routing guard: specialist disowned it, human re-routed
    ESCALATION = "escalation"  # Ch 23 approval queue: a human assigned it by hand


class RoutingSignal(BaseModel):
    """One captured routing event from the trace store (Ch 23).

    Not every signal is a label. `landed_on` is where the request was *handled*;
    `human_confirmed` records whether a human verified that destination. A signal
    that only reflects the LLM router's own decision is **not** a label — training
    on it teaches the adapter to imitate the router's mistakes, the Chapter 13
    "billed twice" → Reporting misroute included.
    """

    request: str
    landed_on: Specialist
    human_confirmed: bool
    source: RouteSource
    trace_id: str  # provenance back to the span (Ch 17)
    occurred_at: datetime


class RoutingExample(BaseModel):
    """A mined training pair: a real request and the human-confirmed route."""

    request: str
    route: Specialist
    source: RouteSource
    trace_id: str
    occurred_at: datetime


def mine_confirmed_routes(signals: Iterable[RoutingSignal]) -> list[RoutingExample]:
    """Keep only human-confirmed routes, then de-duplicate.

    The label is where a request *landed and a human confirmed it* — never the
    router's own output. Dropping the unconfirmed rows is the difference between
    learning the right boundary and imitating the model, mistakes and all.
    """
    confirmed = (
        RoutingExample(
            request=signal.request,
            route=signal.landed_on,
            source=signal.source,
            trace_id=signal.trace_id,
            occurred_at=signal.occurred_at,
        )
        for signal in signals
        if signal.human_confirmed
    )
    return dedupe(confirmed)


def dedupe(examples: Iterable[RoutingExample]) -> list[RoutingExample]:
    """Collapse repeated (request, route) pairs to the first occurrence.

    Production traffic is power-law: the same "where's my invoice" template
    arrives hundreds of times. Left in, it dominates the loss and the adapter
    learns to route *that template* perfectly and everything else badly.
    """
    seen: set[tuple[str, Specialist]] = set()
    out: list[RoutingExample] = []
    for example in examples:
        key = (example.request, example.route)
        if key in seen:
            continue
        seen.add(key)
        out.append(example)
    return out


def class_balance(examples: Sequence[RoutingExample]) -> Counter[Specialist]:
    """Examples per route. The rare class is where aggregate accuracy lies to you."""
    return Counter(example.route for example in examples)


def majority_baseline(examples: Sequence[RoutingExample]) -> float:
    """Accuracy of a model that *always predicts the most common route*.

    The do-nothing floor: if `VENDOR_MGMT` is 3% of traffic, a model that never
    predicts it still scores 97%. Any router has to beat this on *per-class* recall
    (Ch 14), not on the aggregate this number inflates.
    """
    if not examples:
        raise ValueError("cannot compute a baseline over zero examples")
    counts = class_balance(examples)
    return max(counts.values()) / len(examples)


def time_split(
    examples: Sequence[RoutingExample], *, cutoff: datetime
) -> tuple[list[RoutingExample], list[RoutingExample]]:
    """Split train/test on a *date*, never at random.

    Train is everything that arrived before `cutoff`; test is everything at or
    after it. A random split leaks tomorrow's phrasings into today's training set
    and flatters every number you report — Chapter 24 is a whole chapter on this.
    """
    train = [example for example in examples if example.occurred_at < cutoff]
    test = [example for example in examples if example.occurred_at >= cutoff]
    return train, test
