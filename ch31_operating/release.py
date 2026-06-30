"""Discipline 2 — version the prompt and model as deployed artifacts.

The deployed artifact is a *tuple*, not your code: `(code, prompt, model, tools,
config)`, and three of those five change without a commit. Code is versioned by git;
these are the rest, pinned and hashed so "what changed?" is a diff and every trace
can be stamped with the `release_id` that produced it (Chapter 18).

The kill switch lives here too — a config flag on the release that forces every
money-movement tool through `request_approval` regardless of confidence. It is the
operational expression of the risk taxonomy (Chapter 3): when in doubt, drop the
highest-risk tier to human-in-the-loop. It trades throughput for safety in one flip,
and — being a config field — it is part of the versioned tuple, not a code edit.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel

from autopilot import TOOL_RISK, RiskTier

# The kill switch downgrades exactly the irreversible-money tier to human approval.
_KILL_SWITCH_TIERS = frozenset({RiskTier.MONEY_MOVEMENT})


def tool_surface_hash() -> str:
    """A stable hash of the tool menu (name → risk tier). Add, remove, or re-tier a
    tool and the hash — and therefore the release_id — changes. The behavior-
    determining surface, as data."""
    blob = json.dumps(
        {name: tier.value for name, tier in TOOL_RISK.items()}, sort_keys=True
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


class AgentRelease(BaseModel, frozen=True):
    """The behavior-determining tuple, versioned as one artifact.

    `release_id` hashes the three things that change behavior without a commit — the
    prompt, the model, and the tool surface — so two releases are comparable by id and
    every trace can carry the id that produced it.
    """

    prompt_text: str  # the system prompt — prompts are code (Ch 8)
    model_id: str  # the pinned provider model ID (dates badly — App. A)
    tool_schema_hash: str  # hash of the tool surface (see tool_surface_hash)
    eval_suite_sha: str  # the offline suite (Ch 20) this release passed
    kill_switch: bool = False  # force money movement through human approval

    @property
    def release_id(self) -> str:
        """Stable hash of the behavior-determining triple → stamped on every trace."""
        blob = f"{self.prompt_text}|{self.model_id}|{self.tool_schema_hash}"
        return hashlib.sha256(blob.encode()).hexdigest()[:12]


def gated_tool(release: AgentRelease, tool_name: str) -> str:
    """The tool that actually runs, after the kill switch. With the switch flipped, a
    money-movement tool is downgraded to `request_approval`; everything else is
    unchanged. Data-driven off `TOOL_RISK` — never an if/elif on tool names."""
    if release.kill_switch and TOOL_RISK.get(tool_name) in _KILL_SWITCH_TIERS:
        return "request_approval"
    return tool_name


def diff_releases(
    old: AgentRelease, new: AgentRelease
) -> dict[str, tuple[object, object]]:
    """The field-by-field `(old, new)` diff that answers "what changed?". When an
    incident clusters on one `release_id`, this is the revert target, spelled out."""
    old_fields, new_fields = old.model_dump(), new.model_dump()
    return {
        field: (old_fields[field], new_fields[field])
        for field in old_fields
        if old_fields[field] != new_fields[field]
    }
