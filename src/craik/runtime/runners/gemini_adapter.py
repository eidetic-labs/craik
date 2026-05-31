"""Deprecated import path. Use craik.runtime.runners.google_adapter.

Retained for back-compat during the gemini→google rename.
"""

from __future__ import annotations

from craik.runtime.runners.google_adapter import (  # noqa: F401
    GEMINI_ADAPTER_VERSION,
    GEMINI_RUNNER_ID,
    GeminiRunnerAdapter,
    GeminiRunnerAdapterError,
    GeminiRunnerRequestError,
    request_from_compiled_prompt,
)

__all__ = [
    "GEMINI_ADAPTER_VERSION",
    "GEMINI_RUNNER_ID",
    "GeminiRunnerAdapter",
    "GeminiRunnerAdapterError",
    "GeminiRunnerRequestError",
    "request_from_compiled_prompt",
]
