"""Offline tests for tail-based, risk-aware sampling. Pure — no backend, no spend.

The argument the chapter makes is exactly what these pin: the keep/drop decision
reads `RiskTier` from the frozen `TOOL_RISK`, so a money-moving or irreversible
turn is *always* kept while the routine read-only rest is sampled — and the failure
trace survives every time, where uniform sampling would lose it 19 times in 20.
"""

from __future__ import annotations

from .sampling import keep_trace


def _DROP() -> bool:  # a deterministic "the coin said drop"
    return False


def _KEEP() -> bool:  # a deterministic "the coin said keep"
    return True


def test_money_movement_is_always_kept_even_when_the_coin_says_drop() -> None:
    # schedule_payment is MONEY_MOVEMENT in TOOL_RISK → 100% retention.
    assert keep_trace(
        fired=["lookup_invoice", "match_to_po", "schedule_payment"],
        errored=False,
        latency_ms=40,
        sample_routine=_DROP,
    )


def test_an_irreversible_write_is_always_kept() -> None:
    assert keep_trace(
        fired=["post_journal_entry"], errored=False, latency_ms=40, sample_routine=_DROP
    )


def test_a_failure_is_never_dropped() -> None:
    assert keep_trace(fired=[], errored=True, latency_ms=40, sample_routine=_DROP)


def test_a_slow_outlier_is_never_dropped() -> None:
    assert keep_trace(
        fired=["lookup_invoice"], errored=False, latency_ms=10_001, sample_routine=_DROP
    )


def test_a_routine_read_only_turn_obeys_the_sampler() -> None:
    # All read-only, fast, succeeded → a candidate to drop; the coin decides.
    read_only = ["lookup_invoice", "match_to_po", "check_budget", "get_vendor"]
    assert not keep_trace(
        fired=read_only, errored=False, latency_ms=40, sample_routine=_DROP
    )
    assert keep_trace(
        fired=read_only, errored=False, latency_ms=40, sample_routine=_KEEP
    )


def test_an_unknown_tool_name_does_not_crash_and_is_treated_as_routine() -> None:
    # TOOL_RISK.get returns None for an unknown name → not an always-keep tier.
    assert not keep_trace(
        fired=["some_future_tool"], errored=False, latency_ms=40, sample_routine=_DROP
    )


def test_tail_based_keeps_the_failure_every_time_uniform_would_lose_it() -> None:
    # The Try-it-yourself argument: a failing schedule_payment is kept on every
    # draw, whatever the routine sampler returns — uniform 5% keeps it ~1 in 20.
    for coin in (_DROP, _KEEP):
        assert keep_trace(
            fired=["match_to_po", "schedule_payment"],
            errored=True,
            latency_ms=40,
            sample_routine=coin,
        )
