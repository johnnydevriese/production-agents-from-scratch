"""Confidentiality: exfiltration is an output-flow problem, not an input problem.

Chapter 10's three layers all face inward — they stop bad instructions from reaching
the action gate. The cold open's first attack proves that's half a defense: the
secret never had to *enter* as an instruction; it had to *exit* as an answer.
Exfiltration runs the other way through the boundary.

The defense has two halves, and the first is strictly better:

1. **Minimize what the model can read.** The autopilot doesn't need `bank_account`
   to *reason* — only `schedule_payment` needs it, at execution time inside the
   facade. So `get_vendor`, as exposed to the model, returns a *redacted* view: name
   and a masked tail, never the full number. If the model never received it, it
   cannot retype it — and `known_secrets` is empty, so there's nothing to leak.
2. **Scan what the model emits.** A backstop tripwire over outbound text, the same
   kind of trivially-bypassable alert as Chapter 10's keyword list.
"""

from __future__ import annotations

import re
from collections.abc import Set

from pydantic import BaseModel

from autopilot.models import Vendor, VendorId

from ch10_guardrails.guardrails import GuardrailTripped

# Tripwire patterns, NOT the boundary (same caveat as Ch 10's marker list).
_ROUTING = re.compile(r"\b\d{9}\b")  # US routing numbers
_ACCOUNT = re.compile(r"\b\d{7,17}\b")  # bare account-like runs


def mask_account(account: str) -> str:
    """Show only the last four digits — the full number never reaches the model."""
    return f"****{account[-4:]}"


class RedactedVendor(BaseModel):
    """The vendor as the *model* sees it — the bank account masked to a tail."""

    id: VendorId
    name: str
    bank_account_masked: str


def redact_vendor(vendor: Vendor) -> RedactedVendor:
    """The view `get_vendor` returns to the model: enough to reason, nothing to leak."""
    return RedactedVendor(
        id=vendor.id,
        name=vendor.name,
        bank_account_masked=mask_account(vendor.bank_account),
    )


def scan_for_exfiltration(text: str, *, known_secrets: Set[str]) -> None:
    """Raise `GuardrailTripped` if outbound text carries a real secret or its shape.

    The exact-match loop is the real defense — and the reason redaction matters: if
    the model never received the full number, `known_secrets` is empty and there is
    nothing to match. The regex is a bypassable tripwire, valuable as an alert.
    """
    for secret in known_secrets:  # exact match: the real defense
        if secret and secret in text:
            raise GuardrailTripped("outbound text contains a known vendor secret")
    if _ROUTING.search(text) or _ACCOUNT.search(text):
        raise GuardrailTripped("outbound text matches a bank-detail pattern")
