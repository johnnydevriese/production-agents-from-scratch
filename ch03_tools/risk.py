"""Reading the risk tier off a tool name — the half the model never sees.

`TOOL_RISK` (canon, in `autopilot/tools.py`) is the lookup table; these are the
two ways Chapter 3 uses it: name a call's danger before running it, and group the
menu by tier to see which rungs are empty.
"""

from __future__ import annotations

from autopilot.tools import TOOL_RISK, RiskTier


def describe_risk(name: str) -> str:
    """e.g. 'schedule_payment (MONEY_MOVEMENT)'. Raises if the name isn't a tool."""
    return f"{name} ({TOOL_RISK[name].name})"


def group_by_tier() -> dict[RiskTier, list[str]]:
    """Every tier mapped to its tools, in tier order. Empty rungs stay (REVERSIBLE_WRITE)."""
    grouped: dict[RiskTier, list[str]] = {tier: [] for tier in RiskTier}
    for name, tier in TOOL_RISK.items():
        grouped[tier].append(name)
    return grouped
