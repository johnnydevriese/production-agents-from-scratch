"""Print the autopilot's complete repertoire — the divide, rendered.

This checkpoint adds nothing the agent *does*; it adds something *you* do: look
at the capability surface before trusting it. The bounded agent's direct effect
surface is a list of length two you can audit and write a test against. The coding
agent's is a *string*, because the set it describes isn't finite. That contrast is
the whole chapter.

    uv run python -m ch05_divide.action_space
"""

from __future__ import annotations

from autopilot.tools import RiskTier, TOOL_RISK  # the frozen canon from Ch 3

# Anything in this set is a human-gated action, not an autonomous one.
_DANGEROUS = {RiskTier.MONEY_MOVEMENT, RiskTier.IRREVERSIBLE_WRITE}


def describe_bounded() -> str:
    """The orchestration agent's direct effect surface is a list you can read."""
    lines = [f"{name:<20} {tier.value}" for name, tier in TOOL_RISK.items()]
    dangerous = [n for n, t in TOOL_RISK.items() if t in _DANGEROUS]
    lines.append(f"\nTotal actions: {len(TOOL_RISK)}")
    lines.append(f"Actions that can cause harm: {sorted(dangerous)}")  # inspectable
    return "\n".join(lines)


def describe_unbounded() -> str:
    """The coding agent's worst case is one sentence — and it isn't a list."""
    return (
        "Total actions: 1  (run_python)\n"
        "Actions that can cause harm: ['anything the interpreter can reach']"
    )


def main() -> None:
    print(describe_bounded())
    print("\n--- and the coding agent, for contrast ---")
    print(describe_unbounded())


if __name__ == "__main__":
    main()
