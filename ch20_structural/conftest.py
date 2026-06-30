"""Make the real autopilot agent importable offline (see ch11_framework/conftest.py).

Constructing the agent resolves the Anthropic provider eagerly, which needs a key
present even though tests drive a `FunctionModel` and never call the network.
`setdefault` keeps a developer's real key for a live run.
"""

from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-unused-key")
