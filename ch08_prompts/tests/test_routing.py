"""Routing tests — assert the PATH, not the answer. Offline, zero spend.

The broken prompt produced a flawless *summary* and the wrong *work* (it never
matched the PO-less invoice). No answer-quality check distinguishes v1 from v2;
only an assertion over the tool-call path does. So that is what we assert.
"""

from __future__ import annotations

import pytest

from ch08_prompts.agent import run_autopilot
from ch08_prompts.prompt_registry import LIVE_VERSION, load_system_prompt

PO_LESS_INVOICE = (
    "Invoice #DC-2207 — Janitorial services. Amount due: $1,840.00. Net 30."
)
PO_BEARING_INVOICE = (
    "Invoice #INV-1043 from Acme, PO-7781. Amount due: $2,988.09. Net 30."
)


@pytest.mark.parametrize("prompt_version", ["v1", "v2"])
def test_po_less_invoice_always_attempts_match(prompt_version: str) -> None:
    """A PO-less invoice must still trigger match_to_po. v1 is expected to FAIL."""
    trace = run_autopilot(PO_LESS_INVOICE, prompt_version=prompt_version)
    tools_called = [span.tool_name for span in trace.tool_spans]

    if prompt_version == "v1":
        pytest.xfail("v1's narrow trigger skips match_to_po — the bug this ch. fixes")

    assert "match_to_po" in tools_called  # ← the PATH, not the answer


def test_v1_matches_correctly_when_a_po_is_named() -> None:
    """Why the bug survived review: v1 works perfectly on the happy path."""
    trace = run_autopilot(PO_BEARING_INVOICE, prompt_version="v1")
    assert "match_to_po" in [span.tool_name for span in trace.tool_spans]


def test_live_version_is_pinned_and_fixes_the_bug() -> None:
    # The single source of truth points at the fixed prompt…
    assert LIVE_VERSION == "v2"
    # …and the fix is in the prompt text, where a reviewer can diff it.
    assert "Every invoice must be matched" in load_system_prompt(LIVE_VERSION)


def test_a_mispinned_version_fails_loud() -> None:
    with pytest.raises(FileNotFoundError):
        load_system_prompt("v0-does-not-exist")
