"""Chapter 23 — Online evals and monitoring.

Offline evals (Ch 20–22) test the failures someone imagined; production is where
the ones nobody imagined live — a vendor's bank account changed by a phisher,
paid on a textbook-green path. This checkpoint is the loop that learns from that:
cheap, pure **filters** turn the firehose into a small queue, a human judges the
filtered slice, and the confirmed failures are **promoted** into permanent offline
cases that cite the incident.

Everything here is pure (no LLM, no backend): filters and the promote arrow are
functions over a recorded `Trace`. The promote arrow lands a real
`ch24_datasets` `EvalCase` with `origin=MINED` and a `source_trace_id` — so the
provenance the chapter argues for is enforced by Chapter 24's own validator.
"""
