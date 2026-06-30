"""The second refrain, made executable — orchestration vs. coding, side by side.

The whole book turns on one axis: *bound the actions and route, or unbound them
and sandbox.* The AP autopilot (Chapter 11) is the bounded bet — a finite menu of
typed tools, one of which moves money. The analyst (Chapter 7) is the opposite
bet — exactly one general tool, a Python sandbox, and by construction it can read
but never act on the world.

This module reads the *real* agents' tool surfaces and turns the refrain's
comparison table into assertions: the autopilot's menu contains a money-movement
tool; the analyst's contains no `TOOL_RISK` tool at all. Pure introspection — no
model calls, no spend.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent

from autopilot import TOOL_RISK, RiskTier
from ch07_analyst.agent import analyst_agent
from ch11_framework.agent import autopilot


def registered_tools(agent: Agent[Any, Any]) -> frozenset[str]:
    """The names of the tools an agent may call — its action space, as a set.

    There is no stable public sync accessor for this in PydanticAI, so we read the
    same private toolset the Chapter 7 checkpoint does (one isolated access)."""
    return frozenset(agent._function_toolset.tools)  # pyright: ignore[reportPrivateUsage]


class AgentProfile(BaseModel, frozen=True):
    """One row of the orchestration-vs-coding table, computed from a real agent."""

    name: str
    tools: frozenset[str]
    bounded: bool  # is the action space a finite typed menu?
    can_move_money: bool  # does the menu include a money-movement tool?

    @property
    def tool_count(self) -> int:
        return len(self.tools)


def profile(agent: Agent[Any, Any], *, name: str, bounded: bool) -> AgentProfile:
    """Read an agent's action space and decide whether it can move money — the
    answer is whether any tool it holds is classified `MONEY_MOVEMENT`."""
    tools = registered_tools(agent)
    can_move_money = any(
        TOOL_RISK.get(tool) is RiskTier.MONEY_MOVEMENT for tool in tools
    )
    return AgentProfile(
        name=name, tools=tools, bounded=bounded, can_move_money=can_move_money
    )


def autopilot_profile() -> AgentProfile:
    """The bounded orchestration agent — a typed menu including `schedule_payment`."""
    return profile(autopilot, name="AP autopilot", bounded=True)


def analyst_profile() -> AgentProfile:
    """The unbounded coding agent — one sandbox tool, no money tool, ever."""
    return profile(analyst_agent, name="analyst", bounded=False)
