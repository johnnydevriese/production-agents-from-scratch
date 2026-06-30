"""Load a named, versioned system prompt — prompts are code, kept in the repo.

The live version is pinned here, in one place, so "which prompt was in production
at 3pm on the 14th?" has a one-line answer (`git log prompts/`) instead of a
shrug. The broken `v1` is kept on purpose: the regression test proves `v2` fixes
the exact case `v1` missed, and stays fixed.
"""

from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"
LIVE_VERSION = "v2"  # ← the single source of truth for which prompt is in production


def load_system_prompt(version: str = LIVE_VERSION) -> str:
    """Load a named, versioned system prompt. Raises if the version is unknown."""
    path = PROMPTS_DIR / f"system_{version}.md"
    return path.read_text(
        encoding="utf-8"
    )  # FileNotFoundError if mis-pinned — fail loud
