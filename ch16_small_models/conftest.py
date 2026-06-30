"""Make the frontier GL coder importable offline (see ch13_routing/conftest.py).

The student, cascade, mining, calibration, and economics are pure code and spend
nothing. Only `FrontierGLCoder` constructs an `Agent("anthropic:…")`, which resolves
the provider eagerly and needs the key present; its test overrides the model with a
`FunctionModel`, so a placeholder is enough.
"""

from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-unused-key")
