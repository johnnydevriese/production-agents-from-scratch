# ch30_case_study — the improvement loop, run on one incident

One real incident — a misrouted invoice plus a missing idempotency key that nearly
fired a second payment for $2,988.09 — walked end to end through the seven-step loop:
**observe → diagnose → reproduce → add eval → fix → verify → monitor**. The chapter
teaches the *method*; this checkpoint makes its invariants executable. Everything
runs **offline and spends nothing**: the regression case drives the real Chapter 11
autopilot under a `FunctionModel`, and the rest is pure functions over typed data.

## What runs here (offline, 23 tests)

| File | The loop step it makes concrete |
|---|---|
| `incident.py` | ② **diagnose** — the incident and its causal chain as data. `root_cause` is the misroute; the double-pay is a `SYMPTOM`, not the bug. `most_dangerous_fix` is the *silent* one (the loud double-pay is the safe failure). |
| `reproduce.py` | ③ **reproduce** — a deterministic double-pay on Chapter 26's real `IdempotentRail`. Under a forced retry, the unkeyed backwater pays twice; the threaded `payment_idempotency_key` dedupes to one. The only difference is the key. |
| `regression.py` | ④–⑥ **add eval → fix → verify** — the incident as four checks, each *borrowed* from an earlier chapter, over a span tree captured from the real autopilot. Buggy run → four reds; fixed run → four greens. The `paid_exactly_once` check is Chapter 20's real `ToolCallCount`. |
| `monitors.py` | ⑦ **monitor** — the two online checks. A double-pay or empty key **pages**; a misroute is trended, not paged. `policy_for` derives sample rate and paging from the failure's risk tier (`TOOL_RISK`, Chapter 3). |

The case invents no new machinery — it *composes* evaluators the spine already
built: routing (Ch 13–14), tool scoping (Ch 12), the idempotency contract (Ch 26),
`ToolCallCount` (Ch 20), and the online-monitor shape (Ch 23). That is the point: the
loop is a way to *aim* the toolbox at the bug the toolbox predicted.

```bash
# from the repo root
uv run pytest ch30_case_study/ -q
```

## The composition worth re-reading

`regression.silent_variant_run()` is the chapter's sharpest claim, executable: drop
only the routing/scoping fix and keep the idempotency one, and the loud double-pay
*disappears* — no human inbox catches anything — while the real defect (the wrong
agent pays, correctly once) survives. Only `money_movement_only_under_ap` sees it.
The loud bug is the safe one; the silent variant is the trap, which is why the loop
ships defense in depth and why the offline case must assert the *path*, not just the
answer.
