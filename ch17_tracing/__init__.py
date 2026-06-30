"""Chapter 17 — Tracing from first principles.

The Chapter 2 raw-client loop, now wrapped in OpenTelemetry spans: one root
`autopilot.run` span per invoice, a child `chat` span per model call carrying the
`gen_ai.*` semantic conventions, and a child span per tool call named after the
tool and tagged with its frozen risk tier. Tracing is observation, not behavior —
the loop does exactly what Chapter 2's did; it just leaves a readable tree.
"""
