"""Run one request end-to-end: classify with the router, then run the specialist.

The "Acme report" request routes to the reporting specialist — which has no
`schedule_payment` in its menu, so the opening bug is structurally impossible.

    export ANTHROPIC_API_KEY=sk-...
    uv run python -m ch12_multiagent.demo "Give me the reconciliation report for Acme."
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date

from ch06_facade.facade import RailPaymentFacade
from ch06_facade.rail import FakeRail

from .router import router_agent
from .specialists import SPECIALISTS, Deps

_DEFAULT = "Give me the reconciliation report for Acme this month."


async def _run(request: str) -> None:
    deps = Deps(tools=RailPaymentFacade(rail=FakeRail(value_date=date(2026, 6, 30))))
    decision = await router_agent.run(request)  # one cheap classification call
    print(f"[router]   → {decision.output.value}")
    result = await SPECIALISTS[decision.output].run(request, deps=deps)
    print("--- answer ---")
    print(result.output)


def main() -> None:
    asyncio.run(_run(sys.argv[1] if len(sys.argv) > 1 else _DEFAULT))


if __name__ == "__main__":
    main()
