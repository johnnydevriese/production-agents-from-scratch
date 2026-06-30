# ch33_capstone — the autopilot, assembled

The capstone adds no ninth discipline. It *composes* the canon built across the
book into the two artifacts a production agent actually ships behind — a runtime
risk gate and a deploy gauntlet — plus the integration checks that exercise the
**seams**, the places where two correct disciplines were wired together wrong.

All 24 tests are **pure and offline** — no model calls, no spend. The agents are
imported and introspected, never run.

| Module | What it assembles | Reuses | What it pins |
|---|---|---|---|
| `gate.py` | the runtime risk gate | `autopilot.TOOL_RISK` | read-only tools skip payment approval; the three dangerous tiers require a human; an unclassified tool (`extract_invoice`) fails *loud* (KeyError), never defaults to safe |
| `deploy_gate.py` | the four-stage deploy gauntlet | `ch20_structural` (F1), `ch21_stats` (McNemar), `ch31_operating` (canary) | a clean change promotes; the first failing stage stops the line; structural and money-path gates are zero-tolerance; "worse" means *significantly* worse, not one noisy flip |
| `contrast.py` | the orchestration-vs-coding refrain | the real `ch11` autopilot + `ch07` analyst | the AP menu is a bounded typed surface with a money tool; the analyst is one unbounded sandbox tool that holds no `TOOL_RISK` tool at all — only the autopilot can move money |
| `seams.py` | the four composition seams | `ch26` rail via `ch30` reproduction | the catalog covers every wiring boundary; the agent→workflow seam is *executed* — the direct-rail hot-fix double-pays, the durable keyed path pays once |

## The thread

Everything here is *assembly*. Closing the loop required almost no new code because
the span tree, the structural and statistical evaluators, the canary, and the
idempotent rail were all built upstream — the capstone just wires them into one
gate and one decision. The bounded, typed action space (`TOOL_RISK`) is what makes
the assembly tractable: the risk gate is a dict lookup, the deploy gauntlet asserts
over a finite tool surface, and the orchestration-vs-coding contrast is a property
you can read off the two real agents.

## Run

```bash
uv run pytest ch33_capstone/ -q
```
