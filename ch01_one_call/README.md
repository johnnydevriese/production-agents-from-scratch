# ch01_one_call — Chapter 1 checkpoint

The autopilot at its smallest: one Anthropic Messages call that summarizes an
invoice. No loop, no tools, no memory — just text in, text out.

```bash
export ANTHROPIC_API_KEY=sk-...
uv run python summarize_invoice.py
```

- `summarize_invoice.py` — the call, plus a `main()` that prints the *entire*
  response surface (text, stop reason, token usage).
- `sample_invoice.txt` — the fixture the chapter walks through.

What this checkpoint deliberately **cannot** do: look anything up. Ask it whether
the invoice is within budget and it will *guess*. That limitation is what
Chapter 2 fixes by wrapping this call in a loop with tools.
