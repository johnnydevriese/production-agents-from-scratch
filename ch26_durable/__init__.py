"""Chapter 26 — reliability and durable execution.

Every step that touches the outside world will eventually run more than once —
crashes, timeouts, and restarts are involuntary retries. This checkpoint makes the
one un-idempotent tool (`schedule_payment`, the lone `MONEY_MOVEMENT` action) behave
idempotently across re-runs, in two layers:

- `idempotency` — a deterministic key derived from the *work*, so a retry reproduces
  it exactly and the rail dedupes; `rail` is a fake rail that honors it.
- `reliability` — retry only transient faults (never a rejection), and fall back by
  risk tier (a failed money movement stops and asks a human, never "assume it worked").
- `durable` — a small, offline stand-in for a durable-execution engine (Temporal in
  production): completed activities are replayed from a history log, *not* re-run, so a
  crash after `schedule_payment` cannot pay twice, and a multi-day approval wait is a
  zero-cost suspend.

The engine is a teaching model, not Temporal: it captures the one property that
matters — replay-skips-completed-work — so the lesson runs offline at zero spend. The
`README` documents wiring the real `@workflow.defn` against `temporal server start-dev`.
"""
