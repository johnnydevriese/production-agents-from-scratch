"""Exfiltration defense — redact at the read, scan at the write. Pure, no spend.

These pin that the redacted `get_vendor` view carries no full account (so the model
can't retype it), that the outbound scan catches a known secret by exact match, and
— the strictly-better property — that a redacted reply passes precisely *because*
`known_secrets` is empty: the leak was prevented at the read, not caught at the write.
"""

from __future__ import annotations

import pytest

from autopilot import InvoiceId
from autopilot.fixtures import INVOICES, VENDORS

from ch10_guardrails.guardrails import GuardrailTripped

from .exfiltration import mask_account, redact_vendor, scan_for_exfiltration

_VENDOR = VENDORS[
    INVOICES[InvoiceId("INV-1043")].vendor_id
]  # bank_account 000123456789


def test_mask_account_shows_only_the_tail() -> None:
    assert mask_account("000123456789") == "****6789"


def test_the_redacted_view_carries_no_full_account() -> None:
    view = redact_vendor(_VENDOR)
    assert view.bank_account_masked == "****6789"
    assert _VENDOR.bank_account not in view.model_dump_json()  # nothing to retype


def test_a_known_secret_is_caught_on_the_way_out() -> None:
    leak = f"Confirmed — the account on file is {_VENDOR.bank_account}."
    with pytest.raises(GuardrailTripped):
        scan_for_exfiltration(leak, known_secrets=frozenset({_VENDOR.bank_account}))


def test_a_redacted_reply_passes_because_there_is_nothing_to_match() -> None:
    # The model only ever saw the masked tail, so known_secrets is empty.
    reply = "Vendor on file ends in ****6789; please verify against your records."
    scan_for_exfiltration(reply, known_secrets=frozenset())  # no raise


def test_a_bare_routing_pattern_trips_the_backstop() -> None:
    with pytest.raises(GuardrailTripped):
        scan_for_exfiltration("routing is 021000021", known_secrets=frozenset())


def test_clean_text_passes() -> None:
    scan_for_exfiltration(
        "Paid invoice INV-1043 for $2,988.09.", known_secrets=frozenset()
    )
