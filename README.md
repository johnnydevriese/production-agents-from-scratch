# reference-app — the runnable AP autopilot

The companion code for the book **_Production Agents From Scratch_**. It is the
single source of truth for every code listing in the book: each chapter has a
**checkpoint** directory holding the accounts-payable autopilot's code *as of the end
of that chapter* — the previous checkpoint plus the one discipline that chapter adds.
The prose quotes these files; it never invents code. When a printed listing and its
checkpoint ever disagree, **the checkpoint wins** — it is the file that is type-checked
and tested.

## The two rules that make this safe to run

1. **The tests never spend money.** Every checkpoint that calls a language model takes
   its client by dependency injection. You can run it for real against a provider with
   your own key, but the test suite injects a fake client (or a framework `TestModel`)
   that returns scripted responses. So the whole suite type-checks and passes
   **offline, at zero API cost**. A real end-to-end run is always an explicit opt-in,
   never something a test does behind your back.

2. **The checkpoint is the source of truth.** The prose is reconciled to the code, not
   the other way around. To know what the system really does at any point in the book,
   open the checkpoint and run its tests.

## Install & verify (offline, free)

Everything uses [`uv`](https://docs.astral.sh/uv/). Clone the repo and work from this
directory:

```bash
git clone https://github.com/johnnydevriese/production-agents-from-scratch
cd production-agents-from-scratch
uv sync                 # create .venv, install pinned deps from uv.lock
uv run pytest           # the whole suite — offline, free, ~four hundred tests
uv run ruff check .     # lint
uv run basedpyright     # strict type-check, zero errors
```

That is the green-from-clean check. None of it needs an API key, a GPU, or any running
service. The interpreter is pinned by `.python-version` (3.12) and dependencies by
`uv.lock`, so the install is reproducible.

## Run a chapter for real

To watch a checkpoint actually call a model, set a provider key and run that chapter's
demo entry point:

```bash
export ANTHROPIC_API_KEY=sk-...          # your own key; a real run costs a few cents
uv run python -m ch06_facade.agent
```

The checkpoints with extra live-run requirements include a local `README.md`.
For the full checkpoint map, tier, and one-line description of every chapter,
see `RUNNABLE_PLAN.md` or Appendix E of the book.

## Layout

```
production-agents-from-scratch/      ← this repo (the book calls it "the reference-app")
├── autopilot/                ← the frozen canon (Tier 0): types + data, no behavior
│   ├── models.py             ← Invoice, Vendor, Payment, JournalEntry, … + NewType IDs
│   ├── tools.py              ← the seven-tool Protocol, RiskTier, TOOL_RISK
│   ├── router.py             ← Specialist, RouteDecision, Router Protocol
│   └── fixtures.py           ← the offline backend's sample invoices / vendors / POs
├── ch01_one_call/            ← Chapter 1: a single Anthropic Messages call
├── ch02_loop/                ← Chapter 2: the hand-rolled agent loop
│   └── …                     ← ch03 … ch33, one directory per chapter
├── pyproject.toml            ← deps grow chapter by chapter (commented by chapter)
├── uv.lock                   ← pinned, committed for reproducibility
└── RUNNABLE_PLAN.md          ← per-checkpoint status, tiers, and reconciliation notes
```

`autopilot/` is the contract every checkpoint imports. Checkpoints implement behavior
against those types; they never redefine the domain. Checkpoints are otherwise
**additive** — `ch02_loop/` is `ch01_one_call/` plus the loop — so you can diff two
consecutive checkpoints to see exactly what a chapter changed.

## What a *real* run needs (tests are always offline)

| Tier | A live run needs | Examples |
|---|---|---|
| **T1 — pure** | nothing beyond the Python deps | most eval, guardrail, and security chapters |
| **T1.5 — local store** | local SQLite, no server | `ch25_persistence` |
| **T2 — provider API** | an API key, a few ¢/run | the loop, facade, prompting, routing |
| **T3 — local infra** | OTel collector / tracing backend / Temporal | tracing, durable execution |
| **T3 — GPU + ML stack** | a GPU and the training libraries | `ch15_lora`, `ch16_small_models` |

See `RUNNABLE_PLAN.md` for the per-checkpoint tier and a one-line description of each,
or Appendix E of the book for the same map.

## Conventions

- **Frozen stack:** Python 3.12+, `uv`, `ruff`, `basedpyright` (strict), `pydantic`.
  Part I uses the raw provider SDK; **PydanticAI** is adopted around Chapters 6/11 and
  used from then on.
- **The provider in listings is Anthropic's Messages API.** The call shape is the same
  across providers; the lesson transfers.
- **Model IDs and prices date badly.** Treat any specific model name or token price in
  the code as *representative* — Appendix A of the book is where they are kept current.

## License

The code in this repository — every checkpoint and the `autopilot/` canon — is released
under the **MIT License** (see `LICENSE`). Use it, adapt it, ship it. The book's prose
is a separate work and is **not** covered by this license (© 2026 Johnny Devriese, all
rights reserved).
