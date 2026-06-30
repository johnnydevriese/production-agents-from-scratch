# ch18_prod_tracing — production tracing in practice

Chapter 17 made one run's span tree readable. This checkpoint makes a hundred
thousand of them **searchable**. The logic here is backend-agnostic — the chapter's
frozen choice is **Opik**, but the score derivation, the registration payload, and
the sampling rule don't import it, so the whole suite runs offline at zero cost.

## What runs offline (the tests)

- `feedback.py` — `tools_fired` (reads the path from PydanticAI message parts) and
  `derive_feedback` (turns the path into the indexed `tool_called` / `paid` /
  `po_matched` scores). Pure.
- `tracing.py` — `thread_key` (one invoice's case) and `record_turn`, which threads
  a turn then writes its path-scores through an injected `TraceSink`. The tests pass
  a recorder; production passes Opik's `opik_context`.
- `register_scores.py` — the score *definitions* (snake_case payload that fixes the
  recorded gotcha) + an idempotent, DI'd `register`.
- `sampling.py` — tail-based, risk-aware `keep_trace`, driven straight off
  `TOOL_RISK` (Chapter 3).

```bash
uv run pytest ch18_prod_tracing/        # offline, no backend
uv run basedpyright ch18_prod_tracing/
```

## The one service a real run needs: an Opik backend

`opik` is intentionally **not** a project dependency yet (see `pyproject.toml`:
"later chapters add opik…"). To run against a live backend:

```bash
uv add opik httpx
opik configure                  # or self-host: https://github.com/comet-ml/opik
```

Register the definitions once, idempotently — `register` takes the POST by
injection, so you wire it to an `httpx` client aimed at the backend:

```python
import httpx
from ch18_prod_tracing.register_scores import register

with httpx.Client(base_url=OPIK_URL) as client:
    existing = {d["name"] for d in client.get("/feedback-definitions").json()["content"]}
    created = register(
        existing_names=existing,
        post=lambda body: client.post("/feedback-definitions", json=body).raise_for_status(),
    )
    print("created:", created)   # then go verify they appear as filters in the UI
```

Then decorate the turn and pass `opik.opik_context` as the sink:

```python
import opik
from ch18_prod_tracing.tracing import record_turn

@opik.track(name="ap_turn", project_name="ap-autopilot")
async def run_turn(*, invoice_id, session_id, deps) -> str:
    result = await autopilot.run(invoice_id, deps=deps)   # the Ch 17 span tree
    record_turn(
        sink=opik.opik_context,
        invoice_id=invoice_id,
        new_turn_messages=result.new_messages(),
        match=deps.last_match,
    )
    return result.output
```

`opik.opik_context` satisfies `TraceSink` structurally (it exposes
`update_current_trace`). Swap the decorator for Langfuse's `@observe` and the rest
is unchanged — that is the payoff of emitting neutral OTel in Chapter 17.

**Verify the scores land.** Write one turn, then open the backend UI and filter on
`paid = 1`. If the filter isn't offered, your definitions didn't register (the
gotcha) — re-check the payload casing.
