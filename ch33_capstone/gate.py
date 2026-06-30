"""The runtime risk gate — `TOOL_RISK` as a deploy-time and run-time decision.

`TOOL_RISK` (Chapter 3) has been the spine of safety all book. Here it cashes out
as one tiny function the assembled app calls before every tool runs: read-only
tools run the instant the model asks; the dangerous tiers route through human
approval (Chapter 27). Data-driven — a `dict` lookup, never an if/elif on tool
names — and it fails *loud* on a tool nobody classified, because an unknown tool
is the one you least want to run unsupervised.
"""

from __future__ import annotations

from autopilot import TOOL_RISK, RiskTier

# The tiers a money-moving agent never runs unsupervised. Read-only and
# reversible writes skip payment approval; these three demand a human in the loop.
HIGH_RISK = frozenset(
    {RiskTier.MONEY_MOVEMENT, RiskTier.IRREVERSIBLE_WRITE, RiskTier.EXTERNAL_COMMS}
)


def requires_human(tool_name: str) -> bool:
    """Does this tool need human approval before it runs?

    `TOOL_RISK[tool_name]` raises `KeyError` on an unclassified tool rather than
    defaulting to "safe" — fail loud. The separate extraction capability,
    `extract_invoice`, is deliberately absent from the frozen `TOOL_RISK` table,
    so gating it is a setup
    error the gate surfaces instead of swallowing.
    """
    return TOOL_RISK[tool_name] in HIGH_RISK
