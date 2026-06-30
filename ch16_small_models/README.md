# ch16_small_models — distilling the GL-coding step

"Big model decides the path; small model executes the step." Chapter 15 distilled
the **router**; this checkpoint distills a step *inside* the AP specialist — the
GL-coding call that picks the `JournalEntry` accounts before `post_journal_entry`
books them. Everything here runs **offline and spends nothing**: the teacher is
driven by a `FunctionModel`, the student and cascade are deterministic stand-ins,
and the mining, calibration, and economics are pure functions. The one stage that
needs a GPU — fitting the student adapter — reuses Chapter 15's pipeline and is
documented in `ch15_lora/README.md`, not run here.

## What runs here (offline, 23 tests)

| File | What it is |
|---|---|
| `gl_coder.py` | `GLCoding` constrained to a fixed chart of accounts (`GLAccount`); the `GLCoder` Protocol; the `FrontierGLCoder` teacher (injected PydanticAI agent), the `DistilledGLCoder` student (injected `SmallModel`), and `CascadingGLCoder` — student first, fall *up* to the teacher when `confidence < tau`. `to_journal_entry` shows the coding fills the **canonical** `JournalEntry` — no new tool. |
| `mine.py` | Mine training pairs from reviewed decisions: the label is the **final, human-reviewed** account, never the teacher's guess. `corrections` isolates the edited 4% (the teacher's blind spot); `teacher_agreement_rate` is the teacher's grade. |
| `calibration.py` | `reliability_table` + `expected_calibration_error` — the threshold means nothing if the student's confidence is miscalibrated. `threshold_report` shows what a chosen `tau` keeps vs passes up, and that the kept side is more accurate. |
| `economics.py` | `break_even_volume` — below it, the frontier call is the correct engineering decision; above it, the cascade pays. Volume is the entire justification. |

The teacher uses the same injected-agent + `FunctionModel` discipline as
`ch13_routing`'s LLM router; the student's training loop is Chapter 15's, pointed at
a different label space (the chart of accounts instead of the four specialists).

```bash
# from reference-app/
uv run pytest ch16_small_models/ -q
```

## What you wire up for a real run

### Train the student (Chapter 15's pipeline, new label space)

GL coding distills with the *same* mine → train → serve loop as the LoRA router —
only the labels change. Mine pairs with `mine.py` (gold = the corrected account),
then train exactly as `ch15_lora/README.md` documents, with `GLAccount` as the label
space. The student is a `SmallModel`: features in, a `GLCoding` with a **calibrated**
probability out.

```python
# a real SmallModel — a LoRA-adapted small open model behind a local endpoint
class LocalGLModel:
    def __init__(self, *, base_url: str) -> None:
        self._http = httpx.Client(base_url=base_url)

    def classify(self, features: str) -> GLCoding:
        resp = self._http.post("/gl-code", json={
            "features": features,
            "guided_choice": [a.value for a in GLAccount],  # constrained to the chart
        }).raise_for_status().json()
        return GLCoding(**resp)

student = DistilledGLCoder(model=LocalGLModel(base_url="http://localhost:8000"))
coder = CascadingGLCoder(student=student, teacher=build_frontier_gl_coder(), tau=0.90)
```

### Calibrate `tau` before you trust it

Run the student over a held-out, human-graded set and check
`expected_calibration_error`. If it's large, the confidence is a lie and no `tau` is
safe — recalibrate (temperature scaling; Appendix C) before deploying the cascade.
Then pick `tau` against the *asymmetric cost*: a wrong account on a routine supplies
invoice is a cheap correction; a wrong account on a six-figure capital item distorts
the financials.

### Watch it in production (drift is the whole risk)

A GL coder that silently drifts misstates the financials. Wire the student path to an
online eval (Chapter 23) watching the **live correction rate**, with the
un-distilled teacher (`build_frontier_gl_coder()`) as an instant rollback. The model
that was right in June is a liability by December if nobody watches it.

### The DSPy alternative

As in Chapter 15, DSPy optimizes the teacher's *prompt* against the same mined pairs
instead of training a student — lighter MLOps, but still a frontier call per invoice
(so it fixes accuracy, not the cost-at-volume problem this chapter exists to solve).
It needs `dspy-ai` and a frontier API key, so it is not in the offline suite.
