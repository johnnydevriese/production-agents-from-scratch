"""Chapter 29 — Security and trust.

The trust model the Chapter 10 guardrails were missing. Trust is never a property the
model can produce — identity, permission, and the right to see a secret all live in
code, attached to the *request*, not the conversation. This checkpoint is that
principle applied four ways, all pure (no model, no I/O, no spend):

- `security.py` — **authorization**: a request-scoped `SecurityContext` built at the
  edge, and a data-driven role→risk-tier table checked *before* the Ch 10 gate.
  Confirmation is not authorization.
- `exfiltration.py` — **confidentiality**: redact the secret at the *read* (a masked
  `get_vendor` view) and scan outbound text at the *write* as a backstop.
- `audit.py` — **non-repudiation**: an append-only, hash-chained audit trail that
  records who authorized what, written on refusals too, holding no secret.
- `secure_loop.py` — the wiring seam: authorize → gate → dispatch → audit, where the
  *order is the policy*.
"""

from __future__ import annotations
