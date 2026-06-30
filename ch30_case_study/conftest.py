"""Make the real autopilot agent importable offline (see ch11_framework/conftest.py).

The regression case drives the Chapter 11 autopilot, whose construction resolves the
Anthropic provider eagerly and needs a key present — even though every test runs a
`FunctionModel` and never touches the network. `setdefault` keeps a developer's real
key for a live run.
"""

from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-unused-key")
