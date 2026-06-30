"""The hand-checked labeled set the router is scored against.

Each `RoutingCase` is a request plus the route a careful human says it deserves.
The duplicate-charge cases (`gold=AP`) are the Chapter 13 incident, frozen as a
regression guard: a router that sends any of them to `REPORTING` lights the
dangerous `(AP, REPORTING)` cell. At scale these labels are mined from traces and
human approvals (Chapter 15); the design hazards of that are Chapter 24's subject.
"""

from __future__ import annotations

from autopilot import Specialist

from .routing_eval import RoutingCase

GOLDEN_CASES: list[RoutingCase] = [
    RoutingCase(
        request="why was I billed twice for invoice 1043?",
        gold=Specialist.AP,
        note="ch13 duplicate-charge incident",
    ),
    RoutingCase(
        request="I think this was a duplicate payment",
        gold=Specialist.AP,
        note="ch13 duplicate-charge incident",
    ),
    RoutingCase(request="please pay invoice 1043", gold=Specialist.AP),
    RoutingCase(request="remit to the vendor on this charge", gold=Specialist.AP),
    RoutingCase(
        request="match the bank statement to the ledger",
        gold=Specialist.RECONCILIATION,
    ),
    RoutingCase(
        request="reconcile last month's transactions", gold=Specialist.RECONCILIATION
    ),
    RoutingCase(
        request="how much did we spend on cloud this quarter", gold=Specialist.REPORTING
    ),
    RoutingCase(
        request="show the spend trend by department", gold=Specialist.REPORTING
    ),
    RoutingCase(request="onboard a new vendor", gold=Specialist.VENDOR_MGMT),
    RoutingCase(request="update the vendor contact email", gold=Specialist.VENDOR_MGMT),
]
