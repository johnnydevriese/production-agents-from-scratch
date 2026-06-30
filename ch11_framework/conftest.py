"""Make the PydanticAI agent importable offline (see ch06_facade/conftest.py).

`Agent("anthropic:…")` resolves the provider eagerly, which needs the key present
(not validated). Tests override the model with a FunctionModel, so a placeholder
is enough; `setdefault` leaves a real key untouched for a developer's live run.
"""

from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-unused-key")
