"""Three guards around the agent loop — the trust boundary we build in CODE.

The model sees one flat token stream; it cannot tell our instructions from a
malicious PDF's. So we draw the boundary OUTSIDE the model: fence untrusted input
(Layer 1), gate proposed actions against the Chapter 3 risk taxonomy (Layer 2),
and scan output for leaks or parroted orders (Layer 3). The load-bearing layer is
the gate — it fails closed, and the model cannot set the `confirmed` flag that
releases a money-movement call.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from autopilot.tools import TOOL_RISK, RiskTier

logger = logging.getLogger(__name__)


class GuardrailTripped(Exception):
    """A guard refused. The caller decides: block, route to a human, or log."""


# Cheap, deterministic pre-filter — NOT a security boundary, a tripwire for alerting.
_INJECTION_MARKERS = (
    "disregard prior",
    "ignore previous",
    "ignore all",
    "system note",
    "do not flag",
    "do not tell",
    "new instructions",
    "remit payment to",
)


def fence_untrusted(label: str, text: str) -> str:
    """Wrap attacker-controlled text in explicit delimiters the prompt names."""
    for marker in _INJECTION_MARKERS:
        if marker in text.lower():
            # Signal, not verdict: the value is the alert you eval on, not a block.
            logger.warning("injection marker %r in %s", marker, label)
    return f"<untrusted source={label}>\n{text}\n</untrusted source={label}>"


# Tiers that may NEVER fire from an autonomous loop without explicit human assent.
_REQUIRES_CONFIRMATION = frozenset(
    {
        RiskTier.MONEY_MOVEMENT,  # schedule_payment
        RiskTier.IRREVERSIBLE_WRITE,  # post_journal_entry
    }
)


def gate_tool_call(tool_name: str, *, confirmed: bool) -> None:
    """Raise GuardrailTripped if this call must not run unattended.

    No return value — it lets execution continue or refuses. `TOOL_RISK[tool_name]`
    raises KeyError on an unclassified tool, so an invented tool is blocked, not
    silently allowed: new tool, new entry in the canon map, or it cannot run.
    """
    tier = TOOL_RISK[tool_name]  # KeyError on unknown tool = fail closed
    if tier in _REQUIRES_CONFIRMATION and not confirmed:
        raise GuardrailTripped(
            f"{tool_name} is {tier.value}; requires human confirmation before it runs"
        )


def scan_output(reply: str, *, forbidden: Iterable[str] = ()) -> str:
    """Return the reply only if it leaks no secret and parrots no injected order.

    `forbidden` is the set of strings that must never surface — a vendor's
    `bank_account` / `routing_number`. `repr=False` keeps them out of repr/logs,
    but this scanner is the output boundary. An echoed injection marker is the
    second tripwire.
    """
    for secret in forbidden:
        if secret and secret in reply:
            raise GuardrailTripped("output leaks a protected secret")
    lowered = reply.lower()
    for marker in _INJECTION_MARKERS:
        if marker in lowered:
            raise GuardrailTripped(f"output echoes an injected instruction: {marker!r}")
    return reply
