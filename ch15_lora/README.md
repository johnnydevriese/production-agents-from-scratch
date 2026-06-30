# ch15_lora — a LoRA router from scratch

Mine → train → serve → evaluate, pointed at the Chapter 13 router. This checkpoint
runs the three stages that are **pure code** — mining, serving, evaluating — fully
offline and at zero cost. The one stage that genuinely needs a GPU and the ML stack
— fitting the adapter weights — is **documented here, not run in the test suite**.

That split is deliberate and matches the book's contract: every test is offline and
spends nothing. Weight training needs `peft`/`transformers`/`torch` and a GPU; it
produces the same kind of artifact every run (a deterministic adapter), but it is
not something a unit test should provision. So the checkpoint pins the parts that
must be *correct before* you rent a GPU, and this file shows the real training and
serving you wire up around them.

## What runs here (offline, 21 tests)

| File | Stage | What it is |
|---|---|---|
| `mine.py` | 1 — mine | Human-confirmed labels only; dedupe the power-law; `majority_baseline` (the do-nothing floor); `time_split` (hold out by date, never at random). |
| `train.py` | 2 — prep | `to_chat` reuses the LLM router's **exact** system prompt; `LoraSettings` is the frozen config artifact; `corpus_fingerprint` pins the run's identity (same data + seed → same hash). |
| `serve.py` | 3 — serve | `LoRARouter` satisfies the Chapter 13 `Router` Protocol; constrained decoding makes the label always a valid `Specialist`; confidence is the real softmax prob. The forward pass is an injected `InferenceClient` (a fake in tests). |
| `evaluate.py` | 4 — judge | `macro_f1` (exposes the rare-class blind spot), `head_to_head` paired on identical cases, McNemar via `ch21_stats` — gate the swap on the test, not the gap in means. |

The arc is wired through earlier checkpoints, not re-implemented: the label space and
`Router` Protocol come from `autopilot`, the system prompt and cascade from
`ch13_routing`, the per-class metrics from `ch14_routing_eval`, and McNemar's paired
test from `ch21_stats`.

```bash
# from reference-app/
uv run pytest ch15_lora/ -q
```

## What you wire up for a real run (needs a GPU)

### Stage 2 — train the adapter

`train.py` produces the corpus (`build_training_corpus`) and the config
(`LoraSettings`). The real training consumes both:

```bash
uv pip install -r ch15_lora/requirements-gpu.txt
```

`requirements-gpu.txt` is deliberately outside the main `pyproject.toml`: the
core reference app must stay small, offline-testable, and CPU-only, while real
adapter training needs a GPU stack whose wheels vary by platform. If you change
the training stack, update that file in the same commit as the experiment notes.

```python
# the real train step — runs on one modest GPU, minutes-to-an-hour
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

from ch15_lora.train import LoraSettings, build_training_corpus

settings = LoraSettings(base_model="<a small open instruct model, 1-8B>")
rows = [ex.model_dump() for ex in build_training_corpus(train_examples)]

base = AutoModelForCausalLM.from_pretrained(settings.base_model)
tokenizer = AutoTokenizer.from_pretrained(settings.base_model)
lora = LoraConfig(
    r=settings.r,
    lora_alpha=settings.lora_alpha,
    target_modules=settings.target_modules,
    task_type=settings.task_type,
)
trainer = SFTTrainer(
    model=base,
    args=SFTConfig(seed=settings.seed, output_dir="adapter/"),
    peft_config=lora,        # trains ONLY the adapter; the base stays frozen
    train_dataset=rows,
)
trainer.train()              # → a few-MB adapter, not a fork of the base model
```

Same `train_examples` + same `settings.seed` + same `settings.base_model` should
reproduce under a pinned training stack. `corpus_fingerprint(train_examples, settings)`
is the offline proxy for that identity: it changes the instant a label or the seed does.

### Stage 3 — serve the adapter behind `LoRARouter`

`serve.py` is complete as written; you only supply a real `InferenceClient`. The
fake in the tests becomes a thin wrapper over a local inference server that loads the
adapter on the frozen base and decodes with the label set as a hard constraint:

```python
# a real InferenceClient — one small local forward pass, no per-token API bill
class LocalAdapterClient:
    def __init__(self, *, base_url: str) -> None:
        self._http = httpx.Client(base_url=base_url)  # e.g. a local vLLM server

    def classify(self, *, system, user, allowed):
        resp = self._http.post("/classify", json={
            "system": system, "user": user,
            "guided_choice": list(allowed),   # constrained decoding: one of `allowed` only
        }).raise_for_status().json()
        return ClassifyResult(label=resp["label"], prob=resp["prob"])

router = LoRARouter(client=LocalAdapterClient(base_url="http://localhost:8000"))
```

Because `LoRARouter` satisfies the same `Router` Protocol, it drops straight into the
Chapter 13 `CascadeRouter` as the cheap, fast, *learned* middle stage — with the LLM
router behind it as the fall-up for the ambiguous tail.

### The DSPy alternative (try this first)

DSPy optimizes the **prompt** against the same mined labels and touches zero weights
— but it still calls a frontier model to compile and at inference, so it is neither
offline nor free and is therefore **not** in the test suite. The chapter's actual
recommendation is to try it *before* reaching for a GPU:

```bash
uv add dspy-ai           # needs a frontier API key — this path costs money
```

```python
import dspy

class RouteSig(dspy.Signature):
    """Route a finance-ops request to exactly one specialist."""
    request: str = dspy.InputField()
    route: Specialist = dspy.OutputField()      # same frozen label space

# optimize the PROMPT against the SAME stage-1, time-held-out labels:
optimized = dspy.MIPROv2(metric=route_accuracy).compile(
    dspy.Predict(RouteSig), trainset=train_examples,
)
```

Reach for LoRA (this checkpoint) when the binding constraint is **cost at volume,
latency, determinism, or on-prem control** — i.e. when the problem is no longer
accuracy (DSPy can fix that) but the per-request API call itself. That is exactly the
Chapter 14 failure: the LLM router was accurate enough; what it couldn't meet was the
budget.
