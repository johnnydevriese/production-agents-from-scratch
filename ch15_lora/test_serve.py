"""Stage 3 — the learned router honors the frozen contract, with two extras.

These pin: the LoRA router satisfies the Chapter 13 `Router` Protocol (it runs
through Chapter 14's harness unchanged), constrained decoding makes the label
always a valid `Specialist`, the confidence is the score the client returned (not
an invented number), and the router fails closed on an off-menu
label. The forward pass is a deterministic injected fake — offline, no spend.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from autopilot import RouteDecision, Specialist
from ch14_routing_eval.routing_eval import RoutingCase, evaluate

from .serve import ClassifyResult, LoRARouter


class _AdapterClient:
    """A deterministic stand-in for the loaded adapter: keyword -> (label, prob)."""

    def __init__(
        self,
        table: dict[str, tuple[Specialist, float]],
        *,
        default: tuple[Specialist, float],
    ) -> None:
        self._table = table
        self._default = default

    def classify(
        self, *, system: str, user: str, allowed: Sequence[str]
    ) -> ClassifyResult:
        text = user.casefold()
        for keyword, (label, prob) in self._table.items():
            if keyword in text:
                return ClassifyResult(label=label.value, prob=prob)
        label, prob = self._default
        return ClassifyResult(label=label.value, prob=prob)


class _OffMenuClient:
    """A broken adapter that returns a label outside the `Specialist` set."""

    def classify(
        self, *, system: str, user: str, allowed: Sequence[str]
    ) -> ClassifyResult:
        return ClassifyResult(label="payroll", prob=0.99)


def _router() -> LoRARouter:
    return LoRARouter(
        client=_AdapterClient(
            {
                "invoice": (Specialist.AP, 0.96),
                "billed twice": (Specialist.AP, 0.99),
                "reconcile": (Specialist.RECONCILIATION, 0.91),
                "how much": (Specialist.REPORTING, 0.88),
                "onboard": (Specialist.VENDOR_MGMT, 0.83),
            },
            default=(Specialist.REPORTING, 0.40),
        )
    )


def test_it_satisfies_the_router_protocol_and_runs_through_the_ch14_harness() -> None:
    cases = [
        RoutingCase(request="where is invoice INV-1043", gold=Specialist.AP),
        RoutingCase(request="how much did we spend", gold=Specialist.REPORTING),
        RoutingCase(request="onboard a new vendor", gold=Specialist.VENDOR_MGMT),
    ]
    # `evaluate` accepts any `Router`; that this type-checks and runs IS the proof.
    results = evaluate(_router(), cases)
    assert [r.predicted for r in results] == [
        Specialist.AP,
        Specialist.REPORTING,
        Specialist.VENDOR_MGMT,
    ]
    assert all(r.correct for r in results)


def test_the_label_is_always_a_valid_specialist() -> None:
    decision = _router().route("please pay this invoice")
    assert isinstance(decision, RouteDecision)
    assert decision.specialist in set(Specialist)


def test_the_confidence_is_the_score_the_client_returned() -> None:
    # Not an invented number; calibration still decides whether to trust thresholds.
    decision = _router().route("this looks like a duplicate, billed twice")
    assert decision.specialist is Specialist.AP
    assert decision.confidence == pytest.approx(0.99)


def test_it_is_deterministic_for_the_same_request() -> None:
    router = _router()
    first = router.route("how much did we spend last quarter")
    second = router.route("how much did we spend last quarter")
    assert first == second  # zero run-to-run variance, unlike the LLM router (Ch 1)


def test_an_off_menu_label_fails_closed_rather_than_inventing_a_route() -> None:
    router = LoRARouter(client=_OffMenuClient())
    with pytest.raises(ValueError, match="payroll"):
        router.route("run payroll")
