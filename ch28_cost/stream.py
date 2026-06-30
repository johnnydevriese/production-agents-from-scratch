"""Lever 3 — streaming: the p95 is a perception problem (until it isn't).

Streaming delivers output tokens as they're produced. It changes *nothing* about
total compute or cost — the same tokens are generated — but the clerk sees the first
words in a few hundred milliseconds instead of after eleven seconds. The full `usage`
block is still there when the stream closes, so the bill is unaffected.

`consume_stream` models exactly that: it pushes each chunk to the UI sink the instant
it arrives (perceived latency) and returns the accumulated text *plus* the final
usage (the bill). The stream is a Protocol, so a fake drives the test with no network.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol

from pydantic import BaseModel

from .pricing import Usage


class TextStream(Protocol):
    """The slice of a provider stream this code needs: incremental text + final usage."""

    @property
    def text_stream(self) -> Iterable[str]: ...

    def final_usage(self) -> Usage: ...


class StreamResult(BaseModel):
    text: str
    usage: Usage


def consume_stream(stream: TextStream, *, emit: Callable[[str], None]) -> StreamResult:
    """Forward each chunk to the UI as it lands, then return the full text and the bill."""
    chunks: list[str] = []
    for text in stream.text_stream:
        emit(text)  # the clerk sees this immediately — perceived latency collapses
        chunks.append(text)
    return StreamResult(text="".join(chunks), usage=stream.final_usage())
