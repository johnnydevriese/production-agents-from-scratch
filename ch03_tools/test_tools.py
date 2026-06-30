"""Offline tests: schemas match the frozen contract, errors become observations."""

from __future__ import annotations

import inspect
from typing import Any, cast

from anthropic.types import ToolUseBlock

from autopilot.tools import TOOL_RISK, AutopilotTools, RiskTier

from .dispatch import run_tool_calls
from .risk import describe_risk, group_by_tier
from .schema_gen import TOOLS
from .tools_impl import DISPATCH


def _protocol_method_names() -> set[str]:
    return {
        name
        for name, member in vars(AutopilotTools).items()
        if not name.startswith("_") and inspect.isfunction(member)
    }


def _schema_named(name: str) -> dict[str, Any]:
    tool = next(t for t in TOOLS if t["name"] == name)
    return cast("dict[str, Any]", tool["input_schema"])


def test_generated_schemas_cover_every_frozen_tool() -> None:
    names = {t["name"] for t in TOOLS}
    assert names == _protocol_method_names()
    assert names == set(TOOL_RISK)  # every tool the model can call has a risk tier


def test_lookup_invoice_schema_requires_only_invoice_id() -> None:
    schema = _schema_named("lookup_invoice")
    assert schema["required"] == ["invoice_id"]
    assert schema["properties"]["invoice_id"]["type"] == "string"
    assert schema["additionalProperties"] is False


def test_check_budget_amount_is_an_exact_decimal_string_at_the_wire() -> None:
    schema = _schema_named("check_budget")
    assert schema["properties"]["department"]["type"] == "string"
    assert schema["properties"]["amount"]["type"] == "string"


def test_risk_grouping_keeps_the_empty_reversible_rung() -> None:
    grouped = group_by_tier()
    assert "schedule_payment" in grouped[RiskTier.MONEY_MOVEMENT]
    assert grouped[RiskTier.REVERSIBLE_WRITE] == []
    assert set(grouped[RiskTier.READ_ONLY]) == {
        "lookup_invoice",
        "get_vendor",
        "match_to_po",
        "check_budget",
    }


def test_describe_risk_names_the_danger() -> None:
    assert describe_risk("schedule_payment") == "schedule_payment (MONEY_MOVEMENT)"


def test_failed_tool_becomes_an_error_result_not_a_crash() -> None:
    bad = ToolUseBlock(
        type="tool_use", id="toolu_1", name="lookup_invoice", input={"invoice_id": "NOPE"}
    )
    results = run_tool_calls([bad], dispatch=DISPATCH)
    assert len(results) == 1
    assert results[0].get("is_error") is True
    assert results[0]["tool_use_id"] == "toolu_1"


def test_successful_tool_returns_the_invoice_record() -> None:
    good = ToolUseBlock(
        type="tool_use",
        id="toolu_2",
        name="lookup_invoice",
        input={"invoice_id": "INV-1043"},
    )
    results = run_tool_calls([good], dispatch=DISPATCH)
    assert results[0].get("is_error") is not True
    assert "INV-1043" in str(results[0].get("content"))
