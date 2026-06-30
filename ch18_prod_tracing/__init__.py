"""Chapter 18 — Production tracing in practice.

Chapter 17 made one run's span tree readable. This checkpoint makes a hundred
thousand of them *searchable*: automated **feedback scores** derived from the
path (not the answer), grouped into **threads** by case, and a tail-based,
risk-aware **sampling** policy so the bill stays flat.

The logic here is backend-agnostic on purpose — the chapter's frozen choice is
Opik, but the score derivation, the registration payload, and the sampling rule
don't import it. The one Opik-specific seam is a `TraceSink` Protocol (see
`tracing.py`); a real run passes `opik.opik_context`, the tests pass a recorder.
See `README.md` for wiring the live backend.
"""
