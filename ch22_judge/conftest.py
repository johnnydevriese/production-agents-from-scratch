"""Make the judges importable offline (see ch13_routing/conftest.py).

Calibration is pure code and spends nothing. The pointwise and pairwise judges
construct an `Agent("anthropic:…")`, which resolves the provider eagerly and needs
the key present; tests override the model with a FunctionModel, so a placeholder
is enough.
"""

from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-unused-key")
