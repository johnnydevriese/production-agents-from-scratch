"""A small labeled routing set and a deterministic stand-in embedder.

The embedding router learns from labeled examples; this is the offline stand-in for
that label set (the production version is mined from traces in Chapter 15). The
embedder is a 4-axis bag-of-keywords — one axis per `Specialist`, with an epsilon
bias so no vector is zero-length. A request that lights *two* axes is the ambiguous
case the cascade should hand up to the LLM.
"""

from __future__ import annotations

from collections.abc import Sequence

from autopilot import Specialist

_AXES: tuple[Specialist, ...] = (
    Specialist.AP,
    Specialist.RECONCILIATION,
    Specialist.REPORTING,
    Specialist.VENDOR_MGMT,
)
_KEYWORDS: dict[Specialist, tuple[str, ...]] = {
    Specialist.AP: ("invoice", "pay", "charge", "billed", "remit"),
    Specialist.RECONCILIATION: ("match", "statement", "ledger", "reconcile"),
    Specialist.REPORTING: ("trend", "total", "spend", "report", "analytics"),
    Specialist.VENDOR_MGMT: ("onboard", "contact", "vendor"),
}

LABELED_EXAMPLES: list[tuple[str, Specialist]] = [
    ("please pay invoice 1043", Specialist.AP),
    ("this charge looks wrong", Specialist.AP),
    ("match the bank statement to the ledger", Specialist.RECONCILIATION),
    ("reconcile last month's transactions", Specialist.RECONCILIATION),
    ("what did we spend on cloud this quarter", Specialist.REPORTING),
    ("show the spend trend by department", Specialist.REPORTING),
    ("onboard a new vendor", Specialist.VENDOR_MGMT),
    ("update the vendor contact email", Specialist.VENDOR_MGMT),
]


def keyword_embed(text: str) -> Sequence[float]:
    low = text.casefold()
    vector = [0.01, 0.01, 0.01, 0.01]
    for i, axis in enumerate(_AXES):
        if any(keyword in low for keyword in _KEYWORDS[axis]):
            vector[i] += 1.0
    return vector
