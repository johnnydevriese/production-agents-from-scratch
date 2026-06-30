"""Make the PydanticAI agent importable offline.

PydanticAI resolves the Anthropic provider eagerly when `Agent("anthropic:…")`
is constructed, which requires `ANTHROPIC_API_KEY` to be *present* (it isn't
validated until a real call). The tests never make a real call — they override
the model with a `FunctionModel` — so a placeholder is enough. `setdefault`
leaves a real key untouched, so a developer's live run still works.
"""

from __future__ import annotations

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-unused-key")
