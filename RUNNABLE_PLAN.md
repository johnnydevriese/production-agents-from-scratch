# Runnable reference-app — checkpoint map

The runnable-code pass is complete. This document is now the durable checkpoint
map: every chapter checkpoint that should exist has a real directory under
`reference-app/`, every runnable checkpoint is exercised offline by the test
suite, and the prose is reconciled to those files. Chapter 32 is intentionally
conceptual and has no checkpoint.

## The two rules that make this safe to run

1. **Tests never spend money.** Every checkpoint that calls an LLM takes its
   client by dependency injection (`*, client`). The reader runs it against a
   real provider with their own key; our `pytest` suite injects a `FakeAnthropic`
   (or a PydanticAI `TestModel`) that returns scripted responses. So
   `uv run pytest` and `uv run basedpyright` pass **offline, at zero API cost**.
   A real end-to-end run is a documented opt-in (`export ANTHROPIC_API_KEY=…`),
   never part of CI.

2. **The checkpoint is the source of truth; the chapter listing is an excerpt.**
   When a listing and its checkpoint disagree, the type-checked file wins and the
   chapter is corrected to match it. Listings stay labeled illustrative only when
   they are a deliberate simplification of the real file (e.g. "the checkpoint
   generates these schemas from the signatures").

## The canon package (Tier 0 — shared by everything)

`autopilot/` is the frozen contract every checkpoint imports. It holds **types
and data, no behavior**:

| Module | Holds | Status |
|---|---|---|
| `autopilot/models.py` | `Invoice`, `Vendor`, `Payment`, `JournalEntry`, … + `NewType` IDs | ✅ exists |
| `autopilot/tools.py` | `AutopilotTools` Protocol, `RiskTier`, `TOOL_RISK` | ✅ exists |
| `autopilot/router.py` | `Specialist` enum, `RouteDecision`, `Router` Protocol | ✅ exists |
| `autopilot/fixtures.py` | frozen sample invoices/vendors/POs/budgets | ✅ exists |

Checkpoints implement behavior against these types; they do not redefine the
domain. Some duplication of *implementation* across checkpoints is intended —
each `chNN_*/` is a runnable snapshot of the system at that point in the book.

## Dependency tiers (what a *real* run needs — tests are always offline)

| Tier | Needs to run for real | Checkpoints |
|---|---|---|
| **T1 — pure** | nothing (stdlib + pydantic/pydantic-evals/statsmodels/scikit-learn) | `ch03_tools`, `ch05_divide`, `ch19_eval_intro`, `ch20_structural`(evaluators+metrics), `ch21_stats`, `ch22_judge`(calibrate), `ch23_online`, `ch24_datasets`, `ch27_approval`(decision), `ch29_security`, `ch31_operating`(release logic), App. C |
| **T1.5 — local store** | sqlite (no server) | `ch25_persistence` |
| **T2 — provider API** | `ANTHROPIC_API_KEY`, a few ¢/run | `ch02_loop`, `ch04_context`, `ch06_facade`, `ch07_analyst`, `ch08_prompts`, `ch09_structured`, `ch10_guardrails`, `ch11_framework`, `ch12_multiagent`, `ch13_routing`, `ch14_routing_eval`, `ch20_structural`(a real run calls a model), `ch22_judge`(pairwise/reason), `ch28_cost` |
| **T3 — local infra** | OTel collector / Opik server | `ch17_tracing` (runs on a console exporter offline), `ch18_prod_tracing`, `ch23_online` |
| **T3 — Temporal** | `temporal server start-dev` | `ch26_durable` |
| **T3 — GPU + ML stack** | GPU, `peft`/`transformers`/`torch`/`datasets`, `dspy` | `ch15_lora`, `ch16_small_models` |
| **integration** | assembles prior checkpoints (tests stay offline) | `ch30_case_study`, `ch31_operating`, `ch33_capstone` (`ch32` has no checkpoint) |

The checkpoints were built **low-tier-first**: T1 wins are pure profit (no
infra, no spend), T2 is the bulk of the agent itself (DI + fake-client tests),
and T3 keeps the test suite offline while documenting the live service needed
for a real run.

## Build order used (respects cross-checkpoint imports)

1. **Canon**: add `router.py`, `fixtures.py`; wire `pydantic` into deps.
2. **Foundations** (T2/T1): `ch02_loop` → `ch03_tools` → `ch04_context`.
3. **Divide & facade** (T2): `ch05_divide`, `ch06_facade`, `ch07_analyst`.
4. **Prompting & output** (T2/T1): `ch08_prompts`, `ch09_structured`, `ch10_guardrails`.
5. **Framework & routing** (T2): `ch11_framework`, `ch12_multiagent`, `ch13_routing`, `ch14_routing_eval`.
6. **Eval suite** (T1 mostly): `ch20_structural`, `ch21_stats`, `ch22_judge`, `ch24_datasets` (these have the least infra and the most reusable test value).
7. **Observability** (T3): `ch17_tracing`, `ch18_prod_tracing`, `ch23_online`.
8. **Hardening**: `ch27_approval`, `ch28_cost`, `ch29_security` (T1), `ch25_persistence` (T1.5), `ch26_durable` (T3, offline Temporal stand-in) — all built.
9. **ML arc** (T3-GPU): `ch15_lora`, `ch16_small_models` — built import-free (offline dry-run/mocked tests; real training documented in each `README`, not run).
10. **Integration**: `ch30_case_study`, `ch31_operating`, `ch33_capstone`.

## Reconciliation rule, per checkpoint

For each `chNN_*/`: build the real files → run `ruff`, `basedpyright --strict`,
`pytest` → reconcile every fenced listing in the matching chapter against the
file → fix whichever is wrong (file wins) → update the checkpoint status. The
chapter's closing line — *"keep every listing grounded in a file you can open"*
is treated as a release invariant.

## Status

✅ built+tested · 🟡 skeleton+mocked · ⏳ not started. All chapter checkpoints
that should exist are now ✅; historical status markers remain in the table only
where they describe intentionally mocked/live-service boundaries.

All built checkpoints below pass `ruff`, `basedpyright` (strict), and `pytest`
offline — 422 tests (421 pass, 1 intentional `xfail`: the v1 prompt regression),
zero API spend. Each chapter's listings are reconciled against its file. **Every
checkpoint `ch01`→`ch33` is now built — the runnable-code pass is complete.**
(Chapter 19's `ch19_eval_intro/` was the last gap, added during the print-readiness
pass: it makes "path vs answer" runnable on run #4471 before any eval machinery
exists — the hand-built ancestor of Chapter 20's `SpanTree`.)

| Checkpoint | Tier | Status | Notes |
|---|---|---|---|
| `autopilot/` (models, tools, router, fixtures) | T0 | ✅ | the frozen contract; `fixtures` now holds two invoices — INV-1043 (PO) and DC-2207 (PO-less, the Ch 8 exception case) |
| `ch01_one_call` | T2 | ✅ | exemplar; now strict-clean (`cast(TextBlock, …)`) |
| `ch02_loop` | T2 | ✅ | the loop; fake-client tests |
| `ch03_tools` | T1/T2 | ✅ | schemas generated from signatures; risk-labeled, `is_error` dispatch |
| `ch04_context` | T2 | ✅ | accumulate/count/compact + first OTel spans (in-memory exporter); 8 tests |
| `ch05_divide` | T1 | ✅ | renders bounded vs unbounded action surface; harmful set pinned by a test |
| `ch06_facade` | T2 | ✅ | API-facade + PydanticAI agent; pure facade tests (cents/force/idempotency) + FunctionModel wiring; 8 tests |
| `ch07_analyst` | T2 | ✅ | the coding-agent foil — one `run_python` tool, real child-process sandbox (never `exec`), ephemeral seeded workspace; verification-loop test drives buggy→fixed via real exit codes; 9 tests |
| `ch08_prompts` | T2 | ✅ | prompts as code — versioned prompt files + registry; dynamic instructions drive the seven-tool autopilot; a deterministic literal-prompt model proves the PO-less routing bug (`v1` `xfail`, `v2` pass) over the tool-call path; 5 tests |
| `ch09_structured` | T2 | ✅ | the 8th *capability* (`extract_invoice`) — a standalone forced-tool-call extractor (`tool_choice` + `Invoice.model_json_schema()`), NOT an 8th Protocol method; fake-client tests pin the typed `Decimal` total, the forced schema, and a malformed total dying at the boundary; 3 tests |
| `ch10_guardrails` | T1 | ✅ | three guards as pure code — `fence_untrusted` (tripwire that warns, never blocks), `gate_tool_call` (risk-tier gate, fails closed on unknown tools, model can't set `confirmed`), `scan_output` (secret-leak + injection-echo); `settle_or_escalate` proves a tripped gate is a *routing event* (degrades to `request_approval`, rail never disburses); 14 tests |
| `ch11_framework` | T2 | ✅ | the rot fixed on PydanticAI — 7 tools as decorated functions, schemas *derived* from signatures (test pins no-drift); the Ch10 gate wired as a `ModelRetry` validator (degrades to a human, model can't bypass) and `scan_output` as an `@output_validator`; `instrument=True` emits `gen_ai.*` spans, asserted offline via `InMemorySpanExporter`; 5 tests |
| `ch12_multiagent` | T2 | ✅ | the structural fix — one overloaded agent split into a router + four specialists, each a `(prompt, sliced tool-menu)` pair built from a data table (`TOOLS_BY_SPECIALIST`); money movement lives in the AP row alone; a structural test pins that the reporting menu has no `schedule_payment`, and a rogue reporting model still can't pay (`UnexpectedModelBehavior`, rail untouched); router `output_type=Specialist` makes dispatch total/`KeyError`-proof; a typed `MatchResult` handoff (recon → AP) pays on a clean match and holds on a discrepancy; 12 tests |
| `ch13_routing` | T1/T2 | ✅ | four routers behind the frozen `Router` interface — keyword fast-path (pure, abstains with `None`, never defaults), embedding classifier (nearest-centroid over a deterministic stand-in embedder; margin = confidence, clamped to `[0,1]`), LLM router (the one T2 piece, agent injected + driven by `FunctionModel`), fine-tuned deferred to Ch15; a `CascadeRouter` composes them cheap→expensive (proved by an LLM stand-in that *raises if reached*); the re-routing `guard` pins the chapter's core lesson — disown re-routes, hops are bounded (no ping-pong), and exhaustion raises `RouteExhausted` (escalates, never falls back to a default); 13 tests |
| `ch14_routing_eval` | T1/T2 | ✅ | the router scored as a classifier — a pure harness over recorded `RoutingResult`s (no model, no spend): confusion matrix (the `(AP, REPORTING)` cell is the Ch13 bug quantified), per-class precision/recall (AP recall = the safety floor), a data-driven `MISROUTE_COST` matrix so `cost_weighted_error` respects the asymmetry (two routers, equal error *count*, different *cost*), a `confidently_wrong` detector (high confidence + wrong label sails past the Ch13 guard), and `assert_within_budget` as a hard gate (`BudgetExceeded`, never warn-and-pass) — latency (p95) and AP recall measured, dollar cost metered by the provider (Ch28) and passed in; `GOLDEN_CASES` freezes the duplicate-charge incidents as a regression set; 14 tests |
| `ch19_eval_intro` | T1 | ✅ | path vs answer made runnable *before* the eval machinery — pure data, no model. `run.py` freezes run #4471 as an `AgentRun` (a `path` of `ToolCall`s + an `answer`); `checks.py` reads the two properties apart — `answer_cites_invoice` (text-only) stamps #4471 green, `payment_matches_lookup` (path-only) fails it because `lookup_invoice` returned V-ACME but `schedule_payment` paid V-ACMI. `RUN_4471` and a correct `GOOD_RUN` carry the *identical* answer, so the tests pin that the answer check can't tell them apart and only the path check can; the looked-up vendor is read from the shared `INV-1043` fixture so the "truth" can't drift; the hand-built ancestor of `ch20_structural`'s `SpanTree`; 5 tests |
| `ch20_structural` | T1/T2 | ✅ | structural evals over the span tree on **pydantic-evals** — `tool_called`/`ToolNotCalled`/`ToolCallCount`/`ToolCallSequence` query the captured tree (`gen_ai.tool.name`; tool spans are PydanticAI's `execute_tool <name>`, found by attribute key and ordered by `start_timestamp` — the chapter's `name_equals:"running tool"` was stale and reconciled); `ToolCallCount("schedule_payment", 1)` catches the double-pay an `at-least-once` check misses; a pure `metrics.py` scores tool precision/recall/F1 + ordered-transition counts (`ToolCounts` model). The load-bearing rule is enforced by construction: the tests drive the **real ch11 autopilot** (real prompt, schemas, loop) under a `FunctionModel` and a `RecordingTools` boundary fake — never a mocked model — capturing spans via an isolated `InstrumentationSettings(tracer_provider=…)`; markers `span_eval`/`eval_smoke` make the chapter's smoke-lane command real (full-stack lane registered, lands with Ch25/26); 13 tests |
| `ch21_stats` | T1 | ✅ | Wilson + McNemar; tests pin the chapter's figures |
| `ch22_judge` | T1/T2 | ✅ | the LLM-as-judge for the free-text `reason` field (the *answer*, where Ch20 owns the *path*) — a structured `Verdict` whose field order (`evidence_quote` → `reasoning` → `grade`) is load-bearing: a test pins it, because the model generates left-to-right so the grade is conditioned on a quote+rationale that already exist; `judge_reason` is fed the matcher's actual findings so it scores *faithfulness*, not plausibility (a test asserts the discrepancies reach the prompt); `pairwise_winner` runs the swap-and-average position-bias fix — a content-aware stand-in judge proves the better reason wins in **both** orders while a maximally position-biased one collapses to a `tie` (no signal), and a call-counter pins the exact cost (two judge calls per comparison, always); `calibrate` is Cohen's κ (quadratic-weighted, on **scikit-learn**) with the figures pinned — perfect → 1.0, a 4-vs-5 near-miss (κ≈0.97) forgiven far more than a 1-vs-5 (κ=0.60), and a lucky constant judge at 80% raw agreement deflated to κ=0.0; every judge call is offline via an output-tool `FunctionModel`, `demo.py` is the one real-call artifact behind the chapter's command; 12 tests |
| `ch24_datasets` | T1 | ✅ | the dataset as a first-class artifact — pure, no model. A typed `EvalCase` carries path (`expected_tools`/`forbidden_tools`), answer (`answer_must_mention`), and a **required, non-empty `guards`** provenance string (a test pins that an empty or omitted `guards` can't construct), plus an `Origin` enum and a validator forcing `MINED ⇒ source_trace_id`; a `coverage.py` computes the matrix as **cells filled, not rows counted** — a test reproduces the green suite's 142 rows over 3 of 6 cells (`fraction_covered == 0.5`, the whole non-USD column a gap, the `(none, non-USD)` cell the one that paged us) and the curated `dataset.py` closes that column; `split.py` partitions dev/golden by a **stable** SHA-256 id bucket (tested stable across runs, disjoint, complete, ~30% golden) with `assert_no_leakage` (overlap → `LeakageError`) and `assert_golden_eligible` (a fresh `MINED` case → `PrematurePromotionError` until reviewed+reclassified); `mine.py` filters production `Trace`s on the Ch22/Ch23 signals (low judge score, human correction, `EXCEPTION` status) and `promote_to_case` authors a dev-only `MINED` case whose path comes from the **human, not the trace's `tools_called`** (correction-is-a-signal); 14 tests |
| `ch17_tracing` | T3 | ✅ | the Ch 2 raw-client loop, now emitting a span tree (runs offline on an `InMemorySpanExporter`; a `ConsoleSpanExporter` demo for a real run). One root `autopilot.run` per invoice (carries `invoice.id` + an `autopilot.outcome` of `completed`/`needs_approval`), a child `chat` span per model call tagged with the `gen_ai.*` conventions (system/model/operation + usage tokens + finish reasons), and a child span per tool call **named after the tool** and tagged `tool.risk_tier` from the frozen `TOOL_RISK`. `start_as_current_span`'s `with`-nesting builds the parent-child tree (a test pins both children hang off the run); the listing's `result.ok` is made honest (no `.ok` on the models → `tool.ok=True` on return, `False` on a failed lookup, with the exception recorded); a `match_to_po` discrepancy is an **event**, not an attribute (tested); the token climb across two `chat` spans is pinned (1840→2110); and the tracer is **injected** (DI, as Ch 4) so the suite asserts the tree at zero spend; 10 tests |
| `ch18_prod_tracing` | T3 | ✅ | turning 100k traces into a `WHERE` clause — built backend-agnostic so the suite runs offline (`opik` stays an opt-in dep; `README.md` documents the live wiring). `feedback.py` derives the path-scores (`tool_called`/`paid`/`po_matched`) as a **pure** function over PydanticAI message parts — `paid` is true because `schedule_payment` *fired*, not because the model said so (a test pins the incident signature `paid=1 ∧ po_matched=0`); `tracing.py` threads a turn under its invoice-case (`thread_key`) and writes scores through one injected `TraceSink` Protocol (a recorder in tests, `opik.opik_context` in prod); `register_scores.py` is the snake_case definition payload that fixes the recorded casing gotcha (`true_label` pinned, `trueLabel` rejected) + an idempotent DI'd `register`; `sampling.py` is tail-based, risk-aware `keep_trace` reading `RiskTier` from `TOOL_RISK` (money-movement/irreversible kept 100%, routine read-only sampled via an injected ~5% draw) — proven to keep the failure trace every time uniform sampling would lose it 19/20; 19 tests |
| `ch23_online` | T1 | ✅ | the *promote arrow* — production traces become offline cases, built **pure** (no model, no spend). `filters.py` is three signal predicates the structural suite can't see: `smells_like_account_change` (the phished-vendor bank-detail change — a bank account never paid for this `VendorId`), `smells_like_overpay` (payment > 3× the matched PO total, `po_total` injected by the caller so the filter stays pure; an unmatched/PO-less invoice always flags), and an **order-aware** `path_skipped_budget` (a `schedule_payment` with no `check_budget` *before* it — money moved before the check). `triage.py` is a data-driven `FILTERS` table (name → thin `Trace`-level adapter that unpacks the trace into each predicate's kwargs) feeding an injected `AnnotationQueue` Protocol (`ListQueue` in tests); `triage_batch` returns the flagged-ratio shape (21 scanned → 1 flagged) that turns a firehose into a one-item queue. `promote.py` is the whole chapter: `trace_to_eval_case` freezes a confirmed-bad trace into a **real `ch24_datasets` `EvalCase`** with `origin=MINED` + `source_trace_id`, so Ch24's own validator rejects a promotion with no provenance and `assert_golden_eligible` holds a fresh one dev-only until a second human reclassifies it — and the asserted path is the **human's verdict, not the trace's `tools_called`** (a correction is a signal, never ground truth; a test pins `schedule_payment` forbidden, `request_approval` expected); 18 tests |
| `ch27_approval` | T1 | ✅ | approval as a *UI and a logging call*, built pure (no model, no I/O — `persist`/`schedule` are injected). `decision.py` is the record teams drop — `ApprovalDecision` with `trace_id` provenance, `proposed_action_digest` binding the click to the exact payload shown, and a `latency_ms` rubber-stamp tell — and its invariants are enforced *at construction* (a `REJECTED` needs a reason, an `EDITED` needs edits, an `APPROVED` carries none, `decided_at` must be tz-aware; `is_probable_rubber_stamp` fires only on an un-edited near-instant approve). `view.py` builds the three approver panels and computes the policy diff as a **data-driven `POLICY_RULES` table** (first-payment / PO-mismatch / amount-outlier / over-budget) — and `ApprovalView` carries *no* full `bank_account` field, only a masked tail (a test asserts the raw number leaks nowhere in the serialized view — the Ch 29 control). `edits.py` is the bounded surface — `EDITABLE_FIELDS` is exactly the four whitelisted paths (`Vendor.bank_account` deliberately absent), `proposal_digest` hashes the exact `ProposedAction`, `apply_edits` re-validates each correction through Pydantic (a malformed amount dies like the agent's own path), and an edit returns a *new* `ProposedAction` (original never mutated). `capture.py`'s `resolve_approval` refuses a digest mismatch before any persistence, then pins the load-bearing ordering — persist the record *before* money moves (event order `["persist","schedule"]`; a crash in scheduling still leaves the decision durable); 30 tests |
| `ch28_cost` | T1/T2 | ✅ | the four cost/latency levers, built **pure** — cost and latency are arithmetic over the token counts the trace already carries, so the chapter's `client` listings are illustrative and the checkpoint makes the *economics* testable offline. `pricing.py`/`bill.py` make "usage is your bill" executable: `cost_of` prices the four token streams separately (cache *read* ≪ fresh input ≪ cache *write* — the split amortization depends on), `summarize_invoice` folds a trace into one line-item (the ~14,700:830 budget, ~18:1 input-dominated), `preamble_tax` quantifies the re-sent prefix (6 turns × 1,400 → 5 re-sends). `cached_prompt.py` (Lever 1) models the **exact-prefix rule** as a byte-fingerprint (one changed char *or a tool-schema key wobble* → silent miss, both pinned) and the write-premium **amortization** (`preamble_cost` proves caching wins across the loop but *loses* on a one-shot). `cascade.py` (Lever 2) injects the tier callables so escalation is proven with a frontier that raises if reached (Ch 13 pattern) — frontier paid only on the hard tail. `batch.py` (Lever 4) keys batchability off the frozen `TOOL_RISK` (read-only batches; money-movement/irreversible/external-comms don't — batch the thinking, not the wire transfer) + a `Decimal` ~50% async estimate. `stream.py` (Lever 3) consumes a fake stream Protocol — chunks emit as they arrive (perceived latency) while the full `usage` survives (the bill); 22 tests |
| `ch29_security` | T1 | ✅ | the three trust boundaries as four pure modules (side effects injected — zero spend). `security.py` is authorization *before* the Ch 10 gate: a data-driven `_ROLE_MAX_TIER` (viewer→read-only, preparer→+external-comms, approver→every tier) checked by `authorize_tool_call`, which fails closed (`KeyError`) on an unknown tool; `SecurityContext` is built at the edge and its `__repr__` omits the `principal_id` so identity never lands in a log line. `secure_loop.py`'s `secure_dispatch` realizes the chapter's `loop.py` excerpt as one call through `authorize → gate → dispatch → audit` — and a test pins **order is policy**: a viewer who *confirms* a payment raises `Unauthorized` before the gate is reached, the tool never runs, and the only record is `UNAUTHORIZED` (the difference between "a human said yes" and "the *right* human said yes"). `exfiltration.py` is the output-flow defense — `redact_vendor` returns a `RedactedVendor` carrying only `****6789` (a test asserts the full account never appears in `model_dump_json`, so `known_secrets` is empty at the scan — the leak is prevented at the *read*), with `scan_for_exfiltration`'s exact-match loop as the real defense and the regex as a Ch 10-style tripwire. `audit.py` makes privilege non-repudiable: `AuditRecord.outcome` is an `Outcome` enum (not the listing's bare `str`), the record holds no bank/routing field, timestamps must be tz-aware, and `HashChainedAuditLog` is a real hash chain — editing any past record recomputes to a different hash so `verify()` returns `False` (tamper-evidence as a test, written on the refusal too); 22 tests |
| `ch25_persistence` | T1.5 | ✅ | a decision is not an effect — the in-memory eval is blind to the bug because it deletes the subsystem the bug lives in. Built on stdlib `sqlite3` (no server) so the lesson is *real*: every `Store.connect()` is an independent transaction, so an uncommitted write is genuinely invisible to a second connection. `boundary.py` is effect purity made concrete — `schedule_payment` mutates in the session and returns a typed `Payment` but **never commits**; `run_turn(store, work)` is the one transaction owner (commit once on success, roll the whole turn back on any exception, `work` injected so it's testable with no model). The cold-open bug is reproduced as a *passing* test: a turn whose tool ran (Decided + Executed — a span would fire) but then raised leaves the invoice `RECEIVED` with no payment row on a **second connection** (not Committed → not Visible); the same read proves the happy path is durable, a replayed `idempotency_key` trips `UNIQUE` so the boundary rolls back (the same key never pays twice — Ch 26), and a failed turn rolls back the **transcript alongside the effect** so the agent never reads a lie. `memory.py` is the two layers that outlive the process — persisted transcript (`load_thread`) co-committed on the same boundary, and governed episodic `VendorMemory` (provenance + confidence + a `reviewed` gate) where `recall_preferences` returns only reviewed rows, quarantining a planted "remit to account 999" until a human clears it. The four money-path tests carry the `full_stack_eval` marker — the eval chapters' promised full-stack lane is now real; 10 tests |
| `ch26_durable` | T3 | ✅ | reliability + durable execution, built **offline with no Temporal server and no `import temporalio`** (the `ch18`/Opik pattern). `idempotency.py` is the listing verbatim — `payment_idempotency_key` is a pure sha256 over tenant, environment, rail, payment type, vendor, invoice, amount, and currency, so a crash-retry (or a workflow replay) reproduces it exactly while cross-tenant or cross-rail collisions do not; tests pin same-scope→same-key, edited-amount→different-key (a human correction is a *different* payment), scope changes→different-key, and that it's `now()`/`uuid`-free. `rail.py`'s `IdempotentRail` is the other half of the contract — it dedupes on the key so a repeat returns the original confirmation and `transfer_count` stays 1 (a `Rail` Protocol lets the rejecting rail share the shape). `reliability.py` is the cheap moves: `transfer_with_retry` (tenacity, transient-only — a `RailRejection` propagates on the first attempt, never retried; `wait` injectable so tests are instant) and `fallback_for`, a data-driven read of `TOOL_RISK` where `READ_ONLY` degrades and every privileged tier — above all `MONEY_MOVEMENT` — escalates to a human (never "assume it worked"). `durable.py` realizes the `@workflow.defn` workflow as `InvoiceToPayFlow` over a small *teaching* engine (`DurableContext` + a `WorkflowHistory` log) capturing the one property that matters — a completed activity replays from the log, never re-runs. The headline is a *passing* test: a worker that crashes after `schedule_payment` and resumes over the same history re-executes nothing (`activity_runs == 0`), the recorded `Payment` replays, `transfer_count` stays 1 — the duplicate wire is structurally impossible; the multi-day approval wait is `wait_for_signal`/`WorkflowSuspended`, suspending with no payment and resuming on the delivered `decision` signal with the pre-wait activities replayed. `README.md` documents wiring the real Temporal worker; tenacity added to deps; 17 tests |
| `ch15_lora` | T3-GPU | ✅ | a LoRA router from scratch, built **import-free** — the three pure stages run offline; only weight-fitting needs a GPU and is documented in the `README` (not run). `mine.py` is stage-1 hygiene as passing tests: `mine_confirmed_routes` keeps only `human_confirmed` signals (never label from the model's own output — the row an unconfirmed signal would add is dropped), `dedupe` collapses the power-law template, `majority_baseline` is the do-nothing floor (97% by never predicting the rare class), `time_split` holds out by date. `train.py` owns what must be right before a GPU is rented: `to_chat` reuses `ch13`'s `ROUTER_SYSTEM` verbatim (byte-equality pinned) so the head-to-head is fair, `LoraSettings` is the frozen config artifact, and `corpus_fingerprint` is the offline proxy for pinned-stack repeatability (edit a label or the seed and it changes). `serve.py`'s `LoRARouter` satisfies the Ch13 `Router` Protocol — proved by running it straight through Ch14's `evaluate` harness — with the label constrained to a valid `Specialist` (fails closed on an off-menu label) and `confidence` set to the adapter's returned score, not a calibrated probability until calibration proves it. `evaluate.py` is the head-to-head on a time-held-out slice: `macro_f1` exposes the rare-class blind spot aggregate accuracy hides, and `head_to_head` pairs the two routers on identical cases and gates on McNemar — **reusing `ch21_stats`** — so a single net flip reads as noise and a consistent run of gains reads as real; 21 tests |
| `ch16_small_models` | T3-GPU | ✅ | distilling the GL-coding step — "big model decides the path, small model executes the step" — built import-free and offline (the GPU step reuses ch15's pipeline, documented not run). `gl_coder.py` is the spine: `GLCoding` constrained to a fixed `GLAccount` chart (off-chart → `ValidationError`), every coder behind one `GLCoder` Protocol, and `CascadingGLCoder` runs the student first and falls *up* to the teacher only when `confidence < tau` — a test proves the teacher is never called when the student is confident, and that the *same* guess is kept or escalated purely by where `tau` sits (the threshold is the dial); the teacher runs offline under a `FunctionModel` (the ch13 LLM-router discipline), and `to_journal_entry` shows the coding fills the **canonical** `JournalEntry` (no new tool — `post_journal_entry` unchanged). `mine.py` labels from the *final, human-reviewed* account, never the teacher's guess (which would cap the student at the teacher's accuracy), and `corrections` isolates the high-value edited rows. `calibration.py` makes "calibration matters more than accuracy" executable — `expected_calibration_error` catches an overconfident coder (claims 0.99, right half the time → ECE ≈ 0.49) and `threshold_report` shows a calibrated student far more accurate on what it kept than what it passed up (the justification for trusting it). `economics.py`'s `break_even_volume` turns "volume is the whole justification" into a number — below it the frontier call is correct, above it the cascade pays, and a cascade that never trusts the student can never break even; 23 tests |
| `ch30_case_study` | integration | ✅ | the seven-step improvement loop on one incident, built by **composing** the canon (ch11/ch12/ch20/ch26) — no new evaluators. `incident.py` is step ② as ordered data (root cause = the *misroute*, not the loud double-pay symptom; the most dangerous fix is a *silent* one). `reproduce.py` is step ③ on the real ch26 `IdempotentRail`: unstable keys record two transfers, the threaded `payment_idempotency_key` dedupes to one — the double-pay reproduced deterministically offline, not asserted. `regression.py` is steps ④–⑥ as one composed case driving the **real ch11 autopilot** under a `FunctionModel`, captured as a span tree and checked with ch20's `ToolCallCount` + ch12's per-specialist menu: the buggy run trips all four invariants, the fixed run passes all four, and the *silent-variant* run (architecture fix dropped) loses the loud symptom but keeps the real defect. `monitors.py` is step ⑦, risk-tier-driven — the payment-idempotency monitor pages (money-movement tier), the route monitor only trends; 23 tests |
| `ch31_operating` | integration (T1-pure) | ✅ | the four day-2 disciplines, each one module reusing the canon. `oncall.py` (Disc. 1) is the playbook as data — `classify_failure` reads a priority-ordered table top-down (integration error outranks path divergence; an unmatched trace is `NOVEL`), and `should_flip_kill_switch` consults the real `TOOL_RISK` so it flips only for a money-movement misfire. `release.py` (Disc. 2) makes `release_id` a stable hash of the behavior-determining triple (a one-word prompt edit changes it) and `gated_tool` downgrades **only** money-movement tools to `request_approval`, off `TOOL_RISK` — never an if/elif on names. `canary.py` (Disc. 3) gates zero-tolerance on path/money and reuses **ch21**'s Wilson interval (`significant_breaches`) so a 1% slice can't roll back on noise. `drift.py`/`migration.py` (Disc. 4) reuse the same Wilson interval against a reference window and **ch21**'s McNemar — a money-path case flipping pass→fail makes `safe_to_migrate` `False` no matter how strong the rest looks; 34 tests |
| `ch33_capstone` | integration | ✅ | the synthesis — no ninth discipline, only composition into the two artifacts a production agent ships behind. `gate.py` is the runtime risk gate (`requires_human` off `TOOL_RISK`: read-only skips payment approval, the three dangerous tiers need a human, the separate extraction capability `extract_invoice` fails *loud* with `KeyError` if someone incorrectly routes it through the runtime gate). `deploy_gate.py` is the four-stage gauntlet composing **ch20** (tool F1), **ch21** (McNemar), and **ch31** (canary) into one ordered decision — the first failing stage stops the line, structural/money gates zero-tolerance, one noisy regression doesn't block while ten real ones do. `contrast.py` makes the second refrain a test: it reads the **real ch11 autopilot** and **ch07 analyst** tool surfaces and asserts the bounded menu holds a money tool while the unbounded sandbox holds none. `seams.py` catalogs the four composition seams and *executes* the dangerous one — the direct-rail hot-fix double-pays, the durable keyed path pays once (reusing ch30's reproduction on ch26's rail); the assembled agent itself is the real ch11 autopilot; 24 tests |

Proven across the hard tiers already: T1 pure (`ch05`/`ch21`), schema-generation +
risk-aware dispatch (`ch03`), T2 fake-client loop (`ch02`/`ch04`), the first
tracing layer (`ch04`, asserted offline via an `InMemorySpanExporter`), the
**PydanticAI** path (`ch06`: agent constructed offline with a placeholder key via
`conftest.py`, driven by a `FunctionModel`, zero spend), the **coding-agent /
sandbox** path (`ch07`: a real subprocess sandbox runs model code in a child
process — never `exec` — so the verification loop is tested against real exit
codes, still offline and free), and the **prompt-as-router** path (`ch08`:
versioned prompt files loaded as dynamic instructions; a deterministic
literal-prompt stand-in reads the *actual* instructions the agent sent and routes
accordingly, so editing a prompt flips a path test — `xfail`/pass encode the
regression), and the **structured-output / forced-tool** path (`ch09`: a forced
`emit_invoice` tool whose `input_schema` *is* `Invoice.model_json_schema()`, so the
model can only reply by filling typed arguments; the fake client returns one
`ToolUseBlock` and the tests prove the boundary — typed `Decimal` in, malformed
total rejected), and the **guardrails** path (`ch10`: the three guards are pure,
deterministic T1 code tested with no LLM at all — the risk-tier gate fails closed
on unknown tools and a money-movement call degrades to `request_approval` instead
of disbursing, the routing-event thesis proven against the real FakeRail facade),
and the **framework-adoption** path (`ch11`: the same guards and facade on
PydanticAI — derived schemas, the gate as a `ModelRetry` validator, the output scan
as an `@output_validator`, and built-in OTel spans asserted offline), and the
**multi-agent split** path (`ch12`: the menu becomes a data table — one row per
specialist — so "the reporting agent cannot pay" is a fact you assert on the
registered toolset with no model at all; the one model-driven structural test shows
a rogue reporting agent reaching for `schedule_payment` raising
`UnexpectedModelBehavior` while the rail stays empty, and a typed `MatchResult`
handoff proves AP acts on a validated object, not prose — paying a clean match,
holding a discrepancy), and the **routing-layer** path (`ch13`: the routing
decision as a measurable classifier behind one interface — three of the four
routers are pure offline code, and the re-routing guard's escalate-don't-default
rule is pinned by a test that asserts `RouteExhausted` is raised rather than a
default specialist invoked), and the **routing-eval** path (`ch14`: the router
treated as a measurable classifier — a wholly pure harness over recorded results
that needs no model, so a test injects a deterministic stand-in router and asserts
the confusion matrix lights the dangerous `(AP, REPORTING)` cell, that AP recall
falls to the exact fraction expected, that `cost_weighted_error` separates two
routers with identical error counts by *risk*, and that `assert_within_budget`
*raises* on a slow, costly, or low-AP-recall router instead of warning), and the
**structural-eval** path (`ch20`: the first checkpoint on **pydantic-evals** — the
span tree becomes a queryable artifact and structural evals are deterministic
assertions over it; the checkpoint embodies the chapter's hard rule by capturing
spans from the *real* ch11 autopilot driven by a `FunctionModel` over a recording
boundary fake, so `ToolCallCount("schedule_payment", 1)` failing with `got 2` is
proof the **agent** double-paid, not a fixture; a verified gotcha — same-response
tool calls dispatch concurrently — is why the order assertions emit one call per
turn), and the **LLM-as-judge** path (`ch22`: where Ch20 scores the path, the
judge scores the *answer* — the free-text `reason` no assertion can reach; the
structured `Verdict` is the lesson made testable (field order pinned so the grade
follows the evidence), the swap-and-average pairwise fix is proven by a
content-aware stand-in judge that wins in both orders against a position-biased
one that can only tie, and Cohen's κ calibration is pinned to exact figures —
1.0 for perfect, a near-miss forgiven over a far-miss, and an 80%-raw-agreement
constant judge correctly deflated to 0.0 — every judge call offline via an
output-tool `FunctionModel`), and the **dataset-design** path (`ch24`: the thing
the scorers run *over*, built pure — a typed case that can't exist without a
`guards` provenance string, a coverage matrix that counts *cells* so the green
suite's empty non-USD column becomes a failing fact rather than a comfortable
142-row count, a stable-hash dev/golden split with leakage and premature-promotion
guards that make the wall enforceable, and a mining pipeline that turns production
signals into human-authored dev cases — proving by construction that a correction
is a *signal*, not ground truth lifted into an assertion), and the
**tracing-from-first-principles** path (`ch17`: the raw-client loop wrapped by hand
in OpenTelemetry spans — the discipline Ch 11's `instrument=True` and Ch 20's
queryable tree both rest on; `start_as_current_span`'s `with`-nesting *is* the
parent-child tree, so a flat scroll becomes one root `autopilot.run` with `chat`
and tool children, the tool name as the span name and the frozen risk tier as a
filterable attribute, all asserted offline through an `InMemorySpanExporter` with a
scripted client — instrumentation as observation, never behavior), and the
**production-tracing** path (`ch18`: making the haystack searchable, built so the
backend is a swappable detail — the path-derived feedback scores are a pure function
over message parts, threaded and written through one injected `TraceSink` so the
incident query `paid=1 ∧ po_matched=0` is asserted against a recorder with no Opik
server, the snake_case registration payload pins the casing gotcha the real app hit,
and the tail-based sampler reads the Ch 3 `RiskTier` so the trace that moved money is
never the one you dropped), and the **online-eval / promote-arrow** path (`ch23`: the
loop that makes the suite get *smarter*, built wholly pure — three signal filters the
structural suite is blind to (the phished-vendor bank-detail change, an overpay
relative to the matched PO, and an order-aware money-before-budget-check monitor)
compose into a data-driven triage table that turns a 21-trace firehose into a one-item
annotation queue, and `trace_to_eval_case` lands a *real* Ch 24 `MINED` `EvalCase` so
that chapter's own validator enforces the provenance — `source_trace_id` required,
fresh promotions held dev-only — and the asserted path is the human verdict, not the
trace's `tools_called`, proving by construction that a correction is a signal, never
ground truth), and the **human-approval** path (`ch27`: approval as two outputs at
once — a decision that unblocks the workflow and a *decision record* that makes the
agent learnable — built wholly pure with the side effects injected; the record's
invariants are enforced at construction (a reject must say why, an edit must carry
edits, a naive timestamp is refused, `latency_ms` is the rubber-stamp tell), the
editable surface is a four-path whitelist that *cannot* touch `bank_account` and
re-validates every correction so a bad amount dies like the agent's own, the approver
view computes a data-driven policy diff and masks the account so the raw number leaks
nowhere in its serialized form, and `resolve_approval` pins persist-before-act so a
crash between the two never loses the authorization), and the **cost-and-latency**
path (`ch28`: the four levers built as pure arithmetic over the trace's token counts,
no model needed — `cost_of` prices the four token streams separately so the cache
read/write split is honest, `summarize_invoice`/`preamble_tax` read the lopsided
per-invoice bill and quantify the re-sent preamble, the exact-prefix cache rule is a
byte-fingerprint that misses on a one-character or key-order wobble while
`preamble_cost` shows the write premium amortizes across the loop but loses on a
one-shot, the cascade escalates only on low confidence (proven by a frontier that
raises if reached), and batchability reads off the frozen `TOOL_RISK` so the wire
transfer is never batched), and the **security-and-trust** path (`ch29`: the three
trust boundaries built as pure modules over the frozen canon — authorization is a
data-driven role→risk-tier table that fails closed and runs *before* the Ch 10
gate, so `secure_dispatch` proves order-is-policy by raising `Unauthorized` on a
viewer's confirmed payment without the tool ever running or the confirm being
read; exfiltration is defended at the *read* with a `RedactedVendor` that carries
only a masked tail (the full account leaks nowhere in its serialized form, so the
output scan's `known_secrets` is empty by construction) and backstopped by a
Ch 10-style tripwire; and the audit trail is a real hash chain whose `verify()`
catches a tampered record — `outcome` an enum, no bank detail in the row, written
on the refusal too — making privilege non-repudiable as a test, not a promise),
and the **state-and-persistence** path (`ch25`: a decision is not an effect, proven
on real stdlib `sqlite3` rather than a dict that has no transaction to leave
half-open — `run_turn` owns the one transaction per turn so tools stay pure, and the
cold-open bug becomes a *passing* test where a turn's tool ran but nothing committed,
caught only by reading the row back on a **second connection**; a replayed
idempotency key rolls back on the `UNIQUE` constraint, the transcript co-commits with
the effect so the agent never reads a lie, and episodic memory is governed by a
`reviewed` gate that quarantines a planted "remit to account 999" — the four
money-path tests carrying the `full_stack_eval` marker the eval chapters promised),
and the **durable-execution** path (`ch26`: built offline with no Temporal server and
no `import temporalio`, the way `ch18` carries no Opik — a deterministic
`payment_idempotency_key` the rail dedupes on, transient-only retries with a risk-tier
fallback that escalates money movement to a human, and a small teaching engine whose
one property — a completed activity replays from the log, never re-runs — turns the
chapter's headline into a passing test: a worker that crashes after `schedule_payment`
resumes re-executing nothing and `transfer_count` stays 1, the duplicate wire
structurally impossible; the multi-day approval wait is a zero-cost suspend resumed on
a signal, and the README documents the real `@workflow.defn` wiring), and the
**LoRA-router-from-scratch** path (`ch15`: built import-free — only weight-fitting
needs a GPU and is documented, not run — so the three *pure* stages run offline as
passing tests; `mine_confirmed_routes` labels from `human_confirmed` signals and
never the model's own output, `majority_baseline` is the 97%-by-never-predicting-the-rare-class
floor, `time_split` holds out by date; `to_chat` reuses Ch 13's `ROUTER_SYSTEM`
*byte-for-byte* so the head-to-head is fair and `corpus_fingerprint` is the offline
"same inputs to a pinned stack" proxy; the served `LoRARouter` satisfies Ch 13's
`Router` Protocol — proved by running it through **Ch 14's** `evaluate` harness — fails
closed on an off-menu label, and `head_to_head` gates the candidate on McNemar
**reusing `ch21_stats`**, so one net flip reads as noise and a run of gains reads as
real), and the **distill-a-step** path (`ch16`: "big model decides the path, small
model executes the step," built import-free and offline — `GLCoding` constrained to a
fixed chart of accounts, every coder behind one `GLCoder` Protocol, and
`CascadingGLCoder` runs the student first and falls *up* to the teacher only when
`confidence < tau`, proven by a test where the teacher is never called on a confident
student and the *same* guess is kept or escalated purely by where `tau` sits; the
teacher runs offline under a `FunctionModel` and `to_journal_entry` fills the
**canonical** `JournalEntry` with no new tool; `mine.py` labels from the *final,
human-reviewed* account never the teacher's guess, `expected_calibration_error`
catches an overconfident coder a threshold would trust by mistake, and
`break_even_volume` turns "volume is the whole justification" into a number a cascade
that never trusts the student can never reach), and finally the **integration** cluster
that proves the patterns compose (`ch30`: the seven-step improvement loop assembled from
ch11/ch12/ch20/ch26 with the agent's double-pay reproduced on the real rail and a
silent-fix variant that keeps the defect; `ch31`: the four day-2 disciplines, each
reusing ch21's Wilson/McNemar so "worse" and "drifting" are statistical claims, and the
kill switch flipping only the money tier off `TOOL_RISK`; `ch33`: the capstone, where the
runtime risk gate, the four-stage deploy gauntlet over ch20/ch21/ch31, the
orchestration-vs-coding contrast read off the *real* ch07/ch11 agents, and the executed
agent→workflow seam are all *assembly*, not new code).

**The runnable-code pass is complete: `ch01`→`ch33` are built, type-checked, and
reconciled against their chapters — 422 tests (421 pass, 1 intentional `xfail`), zero API
spend, every listing grounded in a file you can open.** `ch32` (architectures revisited)
is prose-only by design — it has no checkpoint.
