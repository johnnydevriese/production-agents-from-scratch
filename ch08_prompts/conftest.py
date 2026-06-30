"""Make the PydanticAI agent importable offline (see ch06_facade/conftest.py).

`Agent("anthropic:…")` resolves the provider eagerly at construction, which needs
`ANTHROPIC_API_KEY` to be *present*. The tests override the model, so the key is
never used; `setdefault` leaves a real one untouched for a live run.
"""

from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-unused-key")
