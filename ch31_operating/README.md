# ch31_operating — the four day-2 disciplines, made executable

Shipping is day 1. This checkpoint is day 2: the disciplines that keep a
money-moving agent honest *after* it's live. Each module is one discipline, and
each one reuses the canon rather than reinventing it — the statistical honesty is
literally Chapter 21's Wilson interval and McNemar test, applied to operations.

All 34 tests are **pure and offline** — no model calls, no spend. They pin the
behavior; the chapter listings are excerpts of these files.

| Module | Discipline | Reuses | What it pins |
|---|---|---|---|
| `oncall.py` | 1 — the on-call playbook | `autopilot.TOOL_RISK` | stabilize first (flip the kill switch only on a money-movement misfire), then classify a trace into a bounded set; an unmatched trace is `NOVEL`, the seed of the next case study |
| `release.py` | 2 — version prompt + model as artifacts | `autopilot.TOOL_RISK` | `release_id` is a stable hash of the behavior-determining triple (prompt, model, tool surface); the kill switch downgrades **only** money movement to `request_approval` |
| `canary.py` | 3 — roll out behind an eval-gated canary | `ch21_stats.intervals.wilson_interval` | path and money gates are zero-tolerance; `significant_breaches` won't roll back on small-sample noise (intervals must separate) |
| `drift.py` | 4a — detect drift before it pages you | `ch21_stats.intervals.wilson_interval` | drift is a statistical claim against a reference window, not a per-trace event; one-directional (worse), interval-gated |
| `migration.py` | 4b — migrate models on purpose | `ch21_stats.compare.paired_eval_test` | a model swap is a new release run through the frozen suite; a money-path regression is an instant stop; "significantly worse" is McNemar, not a vibe |

## The thread through all four

The bounded, typed tool menu is what makes operating an agent a *playbook* rather
than improvisation. Because the action space is explicit, a 2 a.m. failure is
almost always one of a small set (`oncall.FailureClass`); the highest-risk tier is
the only one the kill switch touches (`release.gated_tool`, `oncall.should_flip_kill_switch`);
and "did it get worse?" is always the same question asked four ways — point estimate
for the chapter's listing, interval/McNemar for production truth.

## Run

```bash
uv run pytest ch31_operating/ -q
```
