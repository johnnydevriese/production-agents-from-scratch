"""Chapter 27 — Human approval: the interface, the edit, and the data it creates.

Approval has two outputs, not one: a *decision* that unblocks the workflow, and a
*decision record* that makes the agent smarter. This checkpoint builds the second
output — the part teams drop — as pure, typed code:

- `decision.py` — the `ApprovalDecision` record (provenance + `latency_ms`) and its
  invariants (a reject needs a reason, an edit needs edits, the rubber-stamp tell).
- `view.py` — what the approver must see: proposal + evidence + a policy diff,
  with the vendor's bank details *masked* (the Chapter 29 control).
- `edits.py` — the bounded, typed edit surface: only a whitelist of fields can be
  corrected (never `bank_account`), and an edit produces a new *valid* object.
- `capture.py` — the capture-path discipline: persist the decision record *before*
  any money moves.

Pure T1: no model, no I/O, no spend. The persist/schedule side effects are injected.
"""

from __future__ import annotations
