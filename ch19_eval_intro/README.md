# ch19_eval_intro — path vs answer, made executable

Chapter 19's claim is that an agent run has two independent properties — the
**path** (the work it did) and the **answer** (the text it produced) — and that a
fluent answer can sit on top of a broken path. This checkpoint makes that claim
runnable on **run #4471**, the run that paid the wrong vendor while reporting it
paid the right one.

No model calls, no spend: the run is frozen as data (`run.py`) and the two checks
(`checks.py`) read it directly. It is the hand-built ancestor of Chapter 20, where
the path becomes a real `SpanTree` captured from a live agent.

| File | What it holds |
|---|---|
| `run.py` | `AgentRun` = `path` + `answer`; `RUN_4471` (broken path) and `GOOD_RUN` (correct), grounded in the shared `INV-1043` fixture so the "truth" can't drift |
| `checks.py` | `answer_cites_invoice` (answer-only — green on #4471) and `payment_matches_lookup` (path-only — red on #4471) |
| `test_path_vs_answer.py` | proves the asymmetry: the same answer on both runs, but the path check passes only on the correct one |

The lesson the tests encode: **the answer check and the path check are different
instruments.** A pass on one says nothing about the other — which is why Part VII
builds both columns (structural evals in Chapter 20, LLM-as-judge in Chapter 22).

## Run

```bash
uv run pytest ch19_eval_intro/ -q
```
