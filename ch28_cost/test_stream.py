"""Streaming — pure consumption of a fake stream. No network, no spend.

These pin the two halves of the lever: each chunk reaches the UI the instant it
arrives (perceived latency collapses), and the full `usage` block survives to the end
(the bill is unchanged — streaming is free on cost, paid only in perception).
"""

from __future__ import annotations

from collections.abc import Iterable

from .pricing import Usage
from .stream import consume_stream


class _FakeStream:
    """A canned provider stream: incremental text chunks plus a final usage block."""

    def __init__(self, chunks: list[str], *, usage: Usage) -> None:
        self._chunks = chunks
        self._usage = usage

    @property
    def text_stream(self) -> Iterable[str]:
        return iter(self._chunks)

    def final_usage(self) -> Usage:
        return self._usage


def test_chunks_reach_the_ui_incrementally_and_the_bill_survives() -> None:
    seen: list[str] = []
    stream = _FakeStream(
        ["Sched", "uling ", "payment"],
        usage=Usage(input_tokens=2800, output_tokens=140),
    )

    result = consume_stream(stream, emit=seen.append)

    assert seen == ["Sched", "uling ", "payment"]  # streamed as produced, not buffered
    assert result.text == "Scheduling payment"
    assert result.usage.output_tokens == 140  # the full usage block, for the bill
