"""Make the LLM router importable offline (see ch06_facade/conftest.py).

The keyword fast-path, embedding router, and re-routing guard are pure code and
spend nothing. Only the LLM router constructs an `Agent("anthropic:…")`, which
resolves the provider eagerly and needs the key present; tests override the model
with a FunctionModel, so a placeholder is enough.
"""

from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-unused-key")
