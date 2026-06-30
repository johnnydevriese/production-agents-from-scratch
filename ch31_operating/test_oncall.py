"""The on-call playbook: stabilize first, then classify into a bounded set.

These pin: a money-movement misfire flips the kill switch before any diagnosis; the
classification reads top-down so an integration error outranks a path divergence; an
unmatched trace is NOVEL (the seed of the next case study), not a shrug; and the
responder follows from the class. Pure, no spend.
"""

from __future__ import annotations

from .oncall import (
    FailureClass,
    TraceSymptoms,
    classify_failure,
    responder_for,
    should_flip_kill_switch,
)


def test_a_money_movement_misfire_flips_the_kill_switch_first() -> None:
    assert should_flip_kill_switch(misfiring_tool="schedule_payment")


def test_a_read_only_misfire_does_not_flip_the_kill_switch() -> None:
    # lookup_invoice misbehaving is annoying, not irreversible — diagnose, don't stop.
    assert not should_flip_kill_switch(misfiring_tool="lookup_invoice")
    assert not should_flip_kill_switch(misfiring_tool=None)


def test_an_integration_error_classifies_as_integration_down() -> None:
    symptoms = TraceSymptoms(integration_error=True, path_diverged=True)
    # Read top-down: the throwing tool span outranks the path divergence below it.
    assert classify_failure(symptoms) is FailureClass.INTEGRATION_DOWN


def test_a_wrong_tool_path_is_a_model_regression() -> None:
    symptoms = TraceSymptoms(path_diverged=True)
    assert classify_failure(symptoms) is FailureClass.MODEL_REGRESSION


def test_a_green_path_with_bad_data_is_the_world_moving() -> None:
    symptoms = TraceSymptoms(data_anomaly=True)
    assert classify_failure(symptoms) is FailureClass.WORLD_MOVED


def test_an_aggregate_only_signal_is_drift() -> None:
    symptoms = TraceSymptoms(aggregate_only=True)
    assert classify_failure(symptoms) is FailureClass.DRIFT


def test_an_unmatched_trace_is_novel_not_a_shrug() -> None:
    assert classify_failure(TraceSymptoms()) is FailureClass.NOVEL
    assert "case study" in responder_for(FailureClass.NOVEL)


def test_every_class_has_a_responder() -> None:
    for failure_class in FailureClass:
        assert responder_for(failure_class)
