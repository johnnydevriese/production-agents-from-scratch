"""The curated suite — a small set that is honest about its distribution.

This is deliberately *not* 142 happy-path rows. It spans the four origins, every
case carries a `guards` string, and the coverage tags fill cells the green suite
never had — including the matched/non-USD and PO-less/non-USD cells. The PO-less
EUR services case is the one the green suite was missing: the regression that
freezes the production incident so a model swap can't quietly reintroduce it.
"""

from __future__ import annotations

from autopilot import InvoiceId

from .cases import EvalCase, Origin

_PAY_PATH = [
    "lookup_invoice",
    "match_to_po",
    "check_budget",
    "request_approval",
    "schedule_payment",
    "post_journal_entry",
]

CASES: list[EvalCase] = [
    EvalCase(
        id="happy-usd-matched",
        request="Pay invoice INV-1043.",
        invoice_id=InvoiceId("INV-1043"),
        expected_tools=_PAY_PATH,
        answer_must_mention=["scheduled"],
        origin=Origin.HANDWRITTEN,
        guards="baseline: a clean USD invoice with a matching PO pays end to end.",
        coverage={"po_status": "matched", "currency": "USD"},
    ),
    EvalCase(
        id="po-mismatch-usd",
        request="Pay invoice INV-1051.",
        invoice_id=InvoiceId("INV-1051"),
        expected_tools=["lookup_invoice", "match_to_po", "request_approval"],
        forbidden_tools=["schedule_payment"],
        answer_must_mention=["mismatch", "approval"],
        origin=Origin.REGRESSION,
        guards="surface 5: a quantity mismatch must route to approval, not pay "
        "(incident #4471).",
        coverage={"po_status": "mismatch", "currency": "USD"},
    ),
    EvalCase(
        id="po-less-eur-services",
        request="Pay invoice INV-2208.",
        invoice_id=InvoiceId("INV-2208"),
        expected_tools=["lookup_invoice", "match_to_po", "request_approval"],
        forbidden_tools=["schedule_payment"],
        answer_must_mention=["approval", "no purchase order"],
        origin=Origin.REGRESSION,
        guards="surface 4 ordering: PO-less EUR invoice pressed on to "
        "schedule_payment instead of request_approval (prod incident 2026-06-23).",
        coverage={"po_status": "none", "currency": "non-USD"},
    ),
    EvalCase(
        id="matched-eur",
        request="Pay invoice INV-3300.",
        invoice_id=InvoiceId("INV-3300"),
        expected_tools=_PAY_PATH,
        answer_must_mention=["EUR"],
        origin=Origin.SYNTHETIC,
        guards="fills the matched/non-USD cell the green suite never had — currency "
        "must be carried through, not assumed USD.",
        coverage={"po_status": "matched", "currency": "non-USD"},
    ),
    EvalCase(
        id="duplicate-vendor-name",
        request="Pay the Acme invoice INV-1207.",
        invoice_id=InvoiceId("INV-1207"),
        expected_tools=[
            "lookup_invoice",
            "get_vendor",
            "match_to_po",
            "request_approval",
        ],
        forbidden_tools=["schedule_payment"],
        answer_must_mention=["vendor", "ambiguous"],
        origin=Origin.HANDWRITTEN,
        guards="surface 3 arguments: 'Acme' vs 'Acme Inc' must not resolve to a "
        "wrong get_vendor id and pay.",
        coverage={"po_status": "matched", "currency": "USD"},
    ),
]
