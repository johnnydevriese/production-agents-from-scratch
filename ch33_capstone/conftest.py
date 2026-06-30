"""Make the real agents importable offline (see ch11_framework/conftest.py).

The contrast checks import the Chapter 11 autopilot and the Chapter 7 analyst,
whose construction resolves a provider eagerly and needs a key present — even
though the tests only introspect the tool surface and never touch the network.
`setdefault` keeps a developer's real key for a live `main()` run.
"""

from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-unused-key")
