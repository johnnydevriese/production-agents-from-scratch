"""Make routers importable offline (see ch06_facade/conftest.py).

The harness is pure code; only an LLM router would construct an `Agent`, which
needs the key present. `setdefault` keeps a developer's real key for a live run.
"""

from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-unused-key")
