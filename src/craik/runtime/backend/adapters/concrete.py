"""Concrete per-vendor adapter re-exports (back-compat shim).

Phase 4 rebased every vendor adapter onto ``CLIAdapter`` / ``APIAdapter`` in its
own module. This module now exists ONLY to re-export those real classes so
existing ``from ...concrete import ...`` imports keep resolving:
:class:`AnthropicCLI` (Task 4.1), :class:`AnthropicAPI` (Task 4.2),
:class:`GoogleCLI` (Task 4.3), :class:`GoogleAPI` (Task 4.4),
:class:`OpenAIAPI` (Task 4.5), and :class:`OpenAICLI` (Task 4.6, observe-only).

No stubs remain: the last placeholder (``OpenAICLI`` over a
``_NotImplementedAdapter`` base) was replaced by the real observe-only adapter
in Task 4.6, so the placeholder base is gone.
"""

from __future__ import annotations

from craik.runtime.backend.adapters.anthropic_api import AnthropicAPI
from craik.runtime.backend.adapters.anthropic_cli import AnthropicCLI
from craik.runtime.backend.adapters.google_api import GoogleAPI
from craik.runtime.backend.adapters.google_cli import GoogleCLI
from craik.runtime.backend.adapters.openai_api import OpenAIAPI
from craik.runtime.backend.adapters.openai_cli import OpenAICLI

__all__ = [
    "AnthropicAPI",
    "AnthropicCLI",
    "GoogleAPI",
    "GoogleCLI",
    "OpenAIAPI",
    "OpenAICLI",
]
