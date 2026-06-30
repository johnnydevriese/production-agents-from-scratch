"""Chapter 28 — Cost and latency engineering.

`usage` is your bill and your latency at the same time. This checkpoint is the four
levers that fall out of that sentence, built as pure functions over the token counts
the trace already carries (no model, no spend):

- `pricing.py` — the token→dollars model, with the cache-write/cache-read split.
- `bill.py` — read the per-invoice bill off the trace: the lopsided input:output
  ratio and the re-sent-preamble tax that prompt caching exists to kill.
- `cached_prompt.py` — Lever 1: build the cacheable stable prefix, and the
  exact-prefix rule that makes the cache fail *silently* when a byte wobbles.
- `cascade.py` — Lever 2: cheap model first, escalate up only on low confidence.
- `batch.py` — Lever 4: the ~50% async discount for the work no human waits on,
  and which steps may take it (batch the thinking, never the wire transfer).
- `stream.py` — Lever 3: streaming changes *perceived* latency, not the bill — the
  full `usage` block is still there when the stream closes.
"""

from __future__ import annotations
