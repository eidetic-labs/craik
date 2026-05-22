"""Local model routing presets and health diagnostics."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib import error, request
from urllib.parse import urlparse

from pydantic import Field

from craik.contracts.models import CraikModel, ModelProvider
from craik.runtime.providers.provider_url_safety import (
    ProviderURLSafetyError,
    assert_safe_provider_url,
)

CHAT_COMPLETIONS_PROVIDER_ADAPTER = (
    "craik.runtime.providers.provider_runtime.ChatCompletionsProviderAdapter"
)


class LocalModelPreset(CraikModel):
    """A safe local OpenAI-compatible routing preset."""

    id: str
    name: str
    provider_id: str
    base_url: str
    default_model: str
    health_path: str = "/v1/models"
    config_refs: list[str] = Field(default_factory=list)
    setup_notes: list[str] = Field(default_factory=list)


class LocalModelHealth(CraikModel):
    """Reachability diagnostic for a local model endpoint."""

    preset_id: str
    provider_id: str
    base_url: str
    status: str
    detail: str
    warnings: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


LOCAL_MODEL_PRESETS = (
    LocalModelPreset(
        id="openai-compatible",
        name="Local OpenAI-compatible endpoint",
        provider_id="provider_local_openai_compatible",
        base_url="http://localhost:11434/v1",
        default_model="llama3.2",
        config_refs=[
            "LOCAL_OPENAI_COMPATIBLE_BASE_URL",
            "LOCAL_OPENAI_COMPATIBLE_MODEL",
        ],
        setup_notes=[
            "Use any local server that implements /v1/chat/completions.",
            "No API key is required unless your local endpoint enforces one.",
        ],
    ),
    LocalModelPreset(
        id="ollama",
        name="Ollama OpenAI-compatible endpoint",
        provider_id="provider_local_ollama",
        base_url="http://localhost:11434/v1",
        default_model="llama3.2",
        config_refs=["OLLAMA_BASE_URL", "OLLAMA_MODEL"],
        setup_notes=[
            "Run `ollama serve` and pull the configured model before live use.",
            "Craik talks to Ollama through its OpenAI-compatible /v1 surface.",
        ],
    ),
    LocalModelPreset(
        id="lm-studio",
        name="LM Studio OpenAI-compatible endpoint",
        provider_id="provider_local_lm_studio",
        base_url="http://localhost:1234/v1",
        default_model="local-model",
        config_refs=["LM_STUDIO_BASE_URL", "LM_STUDIO_MODEL"],
        setup_notes=[
            "Start the LM Studio local server before routing live requests.",
            "Use the model id exposed by LM Studio in /v1/models.",
        ],
    ),
    LocalModelPreset(
        id="vllm",
        name="vLLM OpenAI-compatible endpoint",
        provider_id="provider_local_vllm",
        base_url="http://localhost:8000/v1",
        default_model="local-model",
        config_refs=["VLLM_BASE_URL", "VLLM_MODEL"],
        setup_notes=[
            "Start the vLLM OpenAI-compatible server before live use.",
            "Keep the endpoint on loopback unless the sandbox policy explicitly allows more.",
        ],
    ),
)


def list_local_model_presets() -> list[LocalModelPreset]:
    """Return local model presets in stable id order."""
    return sorted(LOCAL_MODEL_PRESETS, key=lambda preset: preset.id)


def require_local_model_preset(preset_id: str) -> LocalModelPreset:
    """Return one local model preset by id."""
    for preset in LOCAL_MODEL_PRESETS:
        if preset.id == preset_id:
            return preset
    known = ", ".join(preset.id for preset in list_local_model_presets())
    raise ValueError(f"unknown local model preset {preset_id!r}; known: {known}")


def provider_for_local_model_preset(
    preset_id: str,
    *,
    base_url: str | None = None,
    model: str | None = None,
) -> ModelProvider:
    """Resolve a preset into no-secret local provider metadata."""
    preset = require_local_model_preset(preset_id)
    resolved_base_url = base_url or preset.base_url
    try:
        assert_safe_provider_url(resolved_base_url, allow_local=True)
    except ProviderURLSafetyError as exc:
        raise ValueError(str(exc)) from exc
    warnings = local_model_base_url_warnings(resolved_base_url)
    return ModelProvider.model_validate(
        {
            "id": preset.provider_id,
            "name": preset.name,
            "provider": "chat_completions",
            "modes": ["chat", "tool", "runner"],
            "capabilities": _local_provider_capabilities(),
            "trust_boundary": "local",
            "config_refs": preset.config_refs,
            "secret_ref_names": [],
            "budget_ref": f"budget_{preset.provider_id.removeprefix('provider_')}_monthly",
            "quota_ref": f"quota_{preset.provider_id.removeprefix('provider_')}_daily",
            "runtime_path": CHAT_COMPLETIONS_PROVIDER_ADAPTER,
            "metadata": {
                "base_url": resolved_base_url,
                "allow_local_base_url": True,
                "default_model": model or preset.default_model,
                "local_model_preset": preset.id,
                "docs_verified": "2026-05-22",
                "warnings": warnings,
            },
            "docs": [
                "docs/guides/local-model-setup.md",
                "docs/guides/provider-routing.md",
                "docs/reference/model-providers.md",
            ],
            "created_at": datetime.now(UTC),
        }
    )


def check_local_model_health(
    preset_id: str,
    *,
    base_url: str | None = None,
    timeout_seconds: float = 2.0,
    opener: Callable[[str, float], dict[str, Any]] | None = None,
) -> LocalModelHealth:
    """Check whether a local OpenAI-compatible endpoint is reachable."""
    preset = require_local_model_preset(preset_id)
    provider = provider_for_local_model_preset(preset_id, base_url=base_url)
    resolved_base_url = str(provider.metadata["base_url"])
    warnings = local_model_base_url_warnings(resolved_base_url)
    health_url = f"{resolved_base_url.rstrip('/')}{preset.health_path}"
    fetch = opener or _fetch_json
    try:
        payload = fetch(health_url, timeout_seconds)
    except (OSError, ValueError) as exc:
        return LocalModelHealth(
            preset_id=preset.id,
            provider_id=preset.provider_id,
            base_url=resolved_base_url,
            status="rejected",
            detail=f"local model endpoint health check failed: {exc}",
            warnings=warnings,
        )
    models = _model_ids(payload)
    return LocalModelHealth(
        preset_id=preset.id,
        provider_id=preset.provider_id,
        base_url=resolved_base_url,
        status="ok" if models else "unknown",
        detail="local model endpoint is reachable"
        if models
        else "local model endpoint responded without model ids",
        warnings=warnings,
        models=models,
    )


def local_model_base_url_warnings(base_url: str) -> list[str]:
    """Return operator warnings for accepted local model base URLs."""
    if urlparse(base_url).scheme != "http":
        return []
    return [
        "WARNING: Local model endpoint uses plaintext HTTP. Acceptable only for "
        "loopback (127.0.0.1/::1). Do NOT bind Ollama to a non-loopback interface."
    ]


def _fetch_json(url: str, timeout_seconds: float) -> dict[str, Any]:
    http_request = request.Request(url, headers={"Accept": "application/json"})
    try:
        # URL scheme and host are validated before this helper is called.
        with request.urlopen(http_request, timeout=timeout_seconds) as response:  # nosec B310
            parsed = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise OSError(f"HTTP {exc.code}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("health response JSON was not an object")
    return parsed


def _model_ids(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data", [])
    if not isinstance(data, list):
        return []
    models: list[str] = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            models.append(item["id"])
    return models


def _local_provider_capabilities() -> list[dict[str, object]]:
    return [
        {
            "name": "model.chat",
            "mode": "chat",
            "description": "Local OpenAI-compatible chat request execution.",
            "grant_required": True,
        },
        {
            "name": "model.tool_calls",
            "mode": "tool",
            "description": "Local OpenAI-compatible tool call support.",
            "grant_required": True,
        },
        {
            "name": "model.structured_output",
            "mode": "chat",
            "description": "Local OpenAI-compatible structured output support.",
            "grant_required": True,
        },
        {
            "name": "model.usage_metadata",
            "mode": "chat",
            "description": "Local OpenAI-compatible usage metadata normalization.",
            "grant_required": False,
        },
        {
            "name": "runner.execute",
            "mode": "runner",
            "description": "Provider-backed local runner execution.",
            "grant_required": True,
        },
    ]


__all__ = [
    "LOCAL_MODEL_PRESETS",
    "LocalModelHealth",
    "LocalModelPreset",
    "check_local_model_health",
    "list_local_model_presets",
    "local_model_base_url_warnings",
    "provider_for_local_model_preset",
    "require_local_model_preset",
]
