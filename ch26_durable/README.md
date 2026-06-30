# ch26_durable — reliability and durable execution

This checkpoint makes the one un-idempotent tool — `schedule_payment`, the lone
`MONEY_MOVEMENT` action — behave idempotently across crashes, retries, and a
multi-day human wait. It runs **offline at zero spend**: there is no Temporal server
and no `import temporalio` anywhere, exactly as `ch18_prod_tracing` carries no
`import opik`. The durable-execution *semantics* are modeled by a small teaching
engine so the lesson is a runnable, deterministic test instead of a promise.

## What's real here vs. what Temporal owns

| Concept (chapter) | In this checkpoint | In production |
|---|---|---|
| Deterministic idempotency key | `idempotency.payment_idempotency_key` — pure sha256 of the work's identity | identical |
| Rail honors the key | `rail.IdempotentRail` dedupes; a repeat returns the same confirmation | a real ACH/wire/card processor's idempotency header |
| Retry transient-only | `reliability.transfer_with_retry` (tenacity, `retry_if_exception_type`) | identical |
| Fallback by risk tier | `reliability.fallback_for` reads `TOOL_RISK` (money → escalate, never "assume worked") | identical |
| **Durable replay** | `durable.DurableContext` records each activity and replays it on re-run | Temporal's event history + replay |
| **Durable pause** | `durable.wait_for_signal` raises `WorkflowSuspended`; resume on a delivered signal | `workflow.wait_condition` + a signal |

The teaching engine captures the **single property that matters**: a completed
activity is replayed from the log, never re-run — so a crash after `schedule_payment`
cannot pay twice. It is *not* Temporal: no worker, no task queue, no real persistence
beyond model JSON in `WorkflowHistory`. Do not ship it.

## Wiring the real engine

Add the dependency where the book does:

```bash
uv add temporalio
temporal server start-dev          # the one service this needs (localhost:7233)
```

Then the offline pieces map directly onto Temporal's primitives:

```python
from temporalio import workflow, activity
from temporalio.client import Client
from temporalio.worker import Worker

# Each tool in TOOL_RISK becomes an activity — this is where ALL side effects live.
@activity.defn
async def schedule_payment(invoice_id: InvoiceId, idempotency_key: str) -> Payment:
    ...  # the ch26 _pay body: rail.transfer(idempotency_key=...) then build Payment

# The agent's "decide the next step" loop becomes the workflow — DETERMINISTIC.
@workflow.defn
class InvoiceToPayWorkflow:
    @workflow.run
    async def run(self, invoice_id: InvoiceId) -> Payment:
        invoice = await workflow.execute_activity(lookup_invoice, invoice_id, start_to_close_timeout=SHORT)
        match = await workflow.execute_activity(match_to_po, invoice_id, start_to_close_timeout=SHORT)
        if match.discrepancies:
            await workflow.execute_activity(request_approval, invoice_id, start_to_close_timeout=SHORT)
            await workflow.wait_condition(lambda: self._decision is not None)   # days are free
        key = payment_idempotency_key(invoice)                                   # INSIDE the workflow
        payment = await workflow.execute_activity(schedule_payment, invoice_id, key, start_to_close_timeout=MEDIUM)
        await workflow.execute_activity(post_journal_entry, _entry_for(payment))
        return payment

    @workflow.signal
    def submit_decision(self, approved: bool) -> None:
        self._decision = approved
```

### The determinism rule (the footgun)

Workflow code is replayed from history on every recovery, so it must be a pure
function of its inputs and the recorded events: **no `datetime.now()`, no `random`, no
direct I/O, no iterating a set whose order isn't stable.** `payment_idempotency_key`
obeys this by construction — it hashes the invoice, never the clock — which is why the
same payment yields the same key on every replay and the rail dedupes the retry. Push
every nondeterministic thing into an activity.

## Run the tests (offline)

```bash
uv run pytest ch26_durable/ -q          # 17 tests, no server, no spend
```
