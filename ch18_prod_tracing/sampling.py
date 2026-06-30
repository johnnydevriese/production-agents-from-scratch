"""Tail-based, risk-aware sampling — because tracing 100% costs like the agent.

A full trace can be as many bytes as the LLM call itself; at 100k/week, storing
all of them rivals the inference bill. The fix is sampling — but *uniform* random
sampling is a trap for an agent that moves money: keep 5% uniformly and you keep
5% of the catastrophic traces, which are exactly the ones you need.

So the decision is **tail-based** (made *after* the turn, by what happened) and
**risk-aware**: it reads `RiskTier` straight from `TOOL_RISK` (Chapter 3). The
tiers that can hurt you — `MONEY_MOVEMENT`, `IRREVERSIBLE_WRITE` — are kept at
100%; an all-read-only, fast, successful turn is a candidate to drop. The taxonomy
that decides *what needs confirmation* doubles as the policy for *what needs a
permanent record*.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Sequence

from autopilot import TOOL_RISK, RiskTier

_ALWAYS_KEEP_TIERS = frozenset({RiskTier.MONEY_MOVEMENT, RiskTier.IRREVERSIBLE_WRITE})
_SLOW_MS = 10_000
_ROUTINE_KEEP_DENOMINATOR = 20  # keep ~1 in 20 ≈ 5% of the routine read-only rest


def _sample_routine() -> bool:
    return secrets.randbelow(_ROUTINE_KEEP_DENOMINATOR) == 0


def keep_trace(
    *,
    fired: Sequence[str],
    errored: bool,
    latency_ms: int,
    sample_routine: Callable[[], bool] = _sample_routine,
) -> bool:
    """Decide whether to retain a finished trace, by risk — not a blind coin flip.

    `sample_routine` is injected so the read-only fraction is testable; it defaults
    to a `secrets`-backed ~5% draw (the project's security standard — a cheaper PRNG
    is fine for a coin flip, but never reach for one where it matters).
    """
    if errored:
        return True  # never drop a failure
    if any(TOOL_RISK.get(name) in _ALWAYS_KEEP_TIERS for name in fired):
        return True  # never drop money movement or an irreversible write
    if latency_ms > _SLOW_MS:
        return True  # never drop a p99 outlier
    return sample_routine()  # keep ~5% of the routine read-only rest
