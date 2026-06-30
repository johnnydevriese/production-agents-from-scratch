"""The router: one cheap classification, then dispatch. It never acts.

`output_type=Specialist` makes "the router can only return one of four labels" a
type guarantee, not a hope — so the dispatch `KeyError` is impossible and the
router has no tool with which to pay, match, or report. It classifies; the chosen
specialist acts, and can only act within its own sliced menu.

This is deliberately thin. Chapter 13 is where it stops being thin: every request
now funnels through this one classifier, which silently caps the quality of
everything downstream. Measuring and hardening that decision is the next chapter.
"""

from __future__ import annotations

from pydantic_ai import Agent

from autopilot import Specialist

from .specialists import MODEL, SPECIALISTS, Deps

router_agent = Agent(
    MODEL,  # Chapter 14: a smaller, cheaper model is fine for classification
    output_type=Specialist,
    system_prompt=(
        "Classify the request into exactly one specialist domain. Do not answer "
        "the request. Do not call tools. Only choose the domain."
    ),
)


async def handle(request: str, *, deps: Deps) -> str:
    """Route one request to one specialist and run it.

    The reporting path *structurally* cannot move money: the agent it lands in has
    no `schedule_payment` in its menu. We didn't fix the opening bug with a better
    prompt — we removed the capability from the agent that handles reports.
    """
    decision = await router_agent.run(request)
    specialist = SPECIALISTS[decision.output]  # KeyError impossible: output is the enum
    result = await specialist.run(request, deps=deps)
    return result.output
