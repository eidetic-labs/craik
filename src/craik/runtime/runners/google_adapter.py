"""Gemini-compatible runner adapter preview."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from craik.contracts.models import CompiledPrompt, RunnerAdapterRequest, RunnerResultStatus
from craik.runtime.runners.preview_adapter import (
    PREVIEW_ADAPTER_VERSION,
    PreviewFixtureAdapter,
)
from craik.runtime.runners.preview_adapter import (
    request_from_compiled_prompt as _preview_request_from_compiled_prompt,
)

GOOGLE_RUNNER_ID = "google"
# Deprecated alias; use GOOGLE_RUNNER_ID (gemini→google rename). Retained so
# legacy run records that reference the "gemini" runner id still resolve.
GEMINI_RUNNER_ID = "gemini"
GOOGLE_ADAPTER_VERSION = PREVIEW_ADAPTER_VERSION
# Deprecated alias; use GOOGLE_ADAPTER_VERSION (gemini→google rename).
GEMINI_ADAPTER_VERSION = GOOGLE_ADAPTER_VERSION


class GeminiRunnerAdapterError(RuntimeError):
    """Base error for Gemini adapter failures."""


class GeminiRunnerRequestError(GeminiRunnerAdapterError):
    """Raised when a request cannot be handled by the Gemini adapter."""


@dataclass(frozen=True)
class GeminiRunnerAdapter(PreviewFixtureAdapter):
    """Preview adapter for Gemini-compatible prompt handoff and fixture runs."""

    runner_id: str = GOOGLE_RUNNER_ID
    display_name: str = "Gemini"
    live_mode: str = "prompt-handoff"
    adapter_version: str = GOOGLE_ADAPTER_VERSION
    fixture_status: RunnerResultStatus = "completed"
    live_available: bool = False
    executable: str | None = None
    metadata_extra: dict[str, Any] = field(default_factory=dict)
    request_error: type[RuntimeError] = GeminiRunnerRequestError


def request_from_compiled_prompt(
    compiled: CompiledPrompt,
    *,
    created_at: datetime | None = None,
    adapter: GeminiRunnerAdapter | None = None,
    context: dict[str, Any] | None = None,
) -> RunnerAdapterRequest:
    """Build a Gemini runner request from a compiled prompt."""
    return _preview_request_from_compiled_prompt(
        compiled,
        runner_id=GOOGLE_RUNNER_ID,
        adapter_factory=GeminiRunnerAdapter,
        request_error=GeminiRunnerRequestError,
        created_at=created_at,
        adapter=adapter,
        context=context,
    )
