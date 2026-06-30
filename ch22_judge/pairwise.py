"""Pairwise judging — "which reason would an AP controller rather receive?"

Pairwise is the most reliable signal a judge produces: models are far better at
"is A better than B" than at "is A a 4 or a 3," because a relative judgment dodges
the question of where the absolute anchors sit. Use it for version bake-offs
(prompt v7 vs v8).

The hazard is **position bias** — judges systematically favor whichever answer is
shown first (some favor the second). The mitigation is mechanical and
non-negotiable: judge (A, B) *and* (B, A), and count a win only if it survives the
swap. A disagreement across orders is the bias talking, so it scores as a tie — no
signal. The cost is exact and unavoidable: two judge calls per comparison. Running
one-sided to save tokens buys a number that flips when you flip the prompt.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName, Model


class PairVerdict(BaseModel):
    reasoning: str = Field(
        description="Why the chosen answer better serves an AP controller."
    )
    winner: Literal["first", "second"]


PAIRWISE_SYSTEM = """You compare two accounts-payable approval reasons written for
an AP controller who must act on them. Choose the one that better names the
specific discrepancy AND the number/next-step the approver needs. Judge
specificity-for-action, not length or polish — a padded reason that restates the
invoice is worse than a crisp one-liner that names the issue. Choose 'first' or
'second'; explain why before you choose."""


def build_pairwise_judge(model: Model | KnownModelName) -> Agent[None, PairVerdict]:
    return Agent(model, output_type=PairVerdict, system_prompt=PAIRWISE_SYSTEM)


def _prompt(*, first: str, second: str) -> str:
    return (
        f"First reason:\n{first!r}\n\n"
        f"Second reason:\n{second!r}\n\n"
        "Which reason better serves an AP controller — 'first' or 'second'?"
    )


def pairwise_winner(a: str, b: str, *, judge: Agent[None, PairVerdict]) -> str:
    """Two-sided pairwise: a win counts only if it survives the swap.

    Returns "a", "b", or "tie". A "tie" means the judge disagreed with itself
    across orders — position bias, not a real signal.
    """
    forward = judge.run_sync(_prompt(first=a, second=b)).output.winner
    reverse = judge.run_sync(_prompt(first=b, second=a)).output.winner
    if forward == "first" and reverse == "second":
        return "a"  # A won in both positions
    if forward == "second" and reverse == "first":
        return "b"  # B won in both positions
    return "tie"  # disagreed across orders → position bias → no signal
