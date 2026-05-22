"""Model provider registry helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from craik.contracts.models import ModelProvider
from craik.runtime.local_models import provider_for_local_model_preset
from craik.runtime.providers.provider_runtime import (
    ANTHROPIC_OFFICIAL_DOCS,
    GEMINI_OFFICIAL_DOCS,
    OPENAI_OFFICIAL_DOCS,
)
from craik.runtime.providers.provider_url_safety import (
    ProviderURLSafetyError,
    assert_safe_provider_url,
)

ANTHROPIC_PROVIDER_ADAPTER = "craik.runtime.providers.provider_runtime.AnthropicProviderAdapter"
GEMINI_PROVIDER_ADAPTER = "craik.runtime.providers.provider_runtime.GeminiProviderAdapter"
OPENAI_PROVIDER_ADAPTER = "craik.runtime.providers.provider_runtime.OpenAIProviderAdapter"
CHAT_COMPLETIONS_PROVIDER_ADAPTER = (
    "craik.runtime.providers.provider_runtime.ChatCompletionsProviderAdapter"
)


class ModelProviderRegistryError(RuntimeError):
    """Base error for model provider registry failures."""


class ModelProviderNotFoundError(ModelProviderRegistryError):
    """Raised when a provider id is not registered."""


class DuplicateModelProviderError(ModelProviderRegistryError):
    """Raised when a provider id is registered twice."""


class ModelProviderRegistry:
    """In-memory registry for model providers and runtime execution paths."""

    def __init__(self, providers: list[ModelProvider] | None = None) -> None:
        self._providers: dict[str, ModelProvider] = {}
        for provider in providers or []:
            self.register(provider)

    def register(self, provider: ModelProvider) -> ModelProvider:
        """Register one provider by stable id."""
        if provider.id in self._providers:
            raise DuplicateModelProviderError(f"provider already registered: {provider.id}")
        _validate_provider_base_url(provider)
        self._providers[provider.id] = provider
        return provider

    def get(self, provider_id: str) -> ModelProvider | None:
        """Return one provider by id, if registered."""
        return self._providers.get(provider_id)

    def require(self, provider_id: str) -> ModelProvider:
        """Return one provider by id or raise a clear error."""
        provider = self.get(provider_id)
        if provider is None:
            raise ModelProviderNotFoundError(f"unknown model provider: {provider_id}")
        return provider

    def list(self) -> list[ModelProvider]:
        """Return registered providers in stable id order."""
        return [self._providers[key] for key in sorted(self._providers)]


def default_model_provider_registry() -> ModelProviderRegistry:
    """Return built-in provider metadata for local and certified MVP workflows."""
    return ModelProviderRegistry(
        [
            ModelProvider.model_validate(
                {
                    "id": "provider_fixture_local",
                    "name": "Fixture Local Provider",
                    "provider": "fixture",
                    "modes": ["chat", "runner"],
                    "capabilities": [
                        {
                            "name": "model.chat",
                            "mode": "chat",
                            "description": "Fixture chat completion.",
                            "grant_required": True,
                        },
                        {
                            "name": "runner.execute",
                            "mode": "runner",
                            "description": "Fixture runner execution.",
                            "grant_required": True,
                        },
                    ],
                    "trust_boundary": "local",
                    "config_refs": ["CRAIK_PROVIDER_FIXTURE_MODE"],
                    "secret_ref_names": ["CRAIK_PROVIDER_FIXTURE_TOKEN"],
                    "budget_ref": "budget_fixture_monthly",
                    "quota_ref": "quota_fixture_daily",
                    "runtime_path": "craik.runtime.fixture_provider",
                    "metadata": {"notes": "Fixture provider metadata only."},
                    "docs": ["docs/reference/model-providers.md"],
                    "created_at": datetime.now(UTC),
                }
            ),
            ModelProvider.model_validate(
                {
                    "id": "provider_anthropic",
                    "name": "Anthropic Claude Provider",
                    "provider": "anthropic",
                    "modes": ["chat", "tool", "runner"],
                    "capabilities": _mvp_provider_capabilities(),
                    "trust_boundary": "third-party",
                    "config_refs": [
                        "CRAIK_ANTHROPIC_MODEL",
                        "CRAIK_ANTHROPIC_BASE_URL",
                        "CRAIK_ANTHROPIC_VERSION",
                    ],
                    "secret_ref_names": ["CRAIK_ANTHROPIC_API_KEY"],
                    "budget_ref": "budget_anthropic_monthly",
                    "quota_ref": "quota_anthropic_daily",
                    "runtime_path": ANTHROPIC_PROVIDER_ADAPTER,
                    "metadata": {
                        "default_model": "claude-sonnet-4-20250514",
                        "docs_verified": "2026-05-17",
                    },
                    "docs": [
                        "docs/reference/model-providers.md",
                        "docs/reference/provider-certification.md",
                        *ANTHROPIC_OFFICIAL_DOCS,
                    ],
                    "created_at": datetime.now(UTC),
                }
            ),
            ModelProvider.model_validate(
                {
                    "id": "provider_openai",
                    "name": "OpenAI Provider",
                    "provider": "openai",
                    "modes": ["chat", "tool", "runner"],
                    "capabilities": _mvp_provider_capabilities(),
                    "trust_boundary": "third-party",
                    "config_refs": [
                        "CRAIK_OPENAI_MODEL",
                        "CRAIK_OPENAI_BASE_URL",
                    ],
                    "secret_ref_names": ["CRAIK_OPENAI_API_KEY"],
                    "budget_ref": "budget_openai_monthly",
                    "quota_ref": "quota_openai_daily",
                    "runtime_path": OPENAI_PROVIDER_ADAPTER,
                    "metadata": {
                        "default_model": "gpt-5.2",
                        "docs_verified": "2026-05-17",
                    },
                    "docs": [
                        "docs/reference/model-providers.md",
                        "docs/reference/provider-certification.md",
                        *OPENAI_OFFICIAL_DOCS,
                    ],
                    "created_at": datetime.now(UTC),
                }
            ),
            ModelProvider.model_validate(
                {
                    "id": "provider_gemini",
                    "name": "Google Gemini Provider",
                    "provider": "gemini",
                    "modes": ["chat", "tool", "runner"],
                    "capabilities": _mvp_provider_capabilities(),
                    "trust_boundary": "third-party",
                    "config_refs": [
                        "CRAIK_GEMINI_MODEL",
                        "CRAIK_GEMINI_BASE_URL",
                    ],
                    "secret_ref_names": ["CRAIK_GEMINI_API_KEY"],
                    "budget_ref": "budget_gemini_monthly",
                    "quota_ref": "quota_gemini_daily",
                    "runtime_path": GEMINI_PROVIDER_ADAPTER,
                    "metadata": {
                        "base_url": "https://generativelanguage.googleapis.com",
                        "default_model": "gemini-2.5-pro",
                        "docs_verified": "2026-05-22",
                    },
                    "docs": [
                        "docs/reference/model-providers.md",
                        "docs/reference/provider-certification.md",
                        *GEMINI_OFFICIAL_DOCS,
                    ],
                    "created_at": datetime.now(UTC),
                }
            ),
            ModelProvider.model_validate(
                {
                    "id": "provider_anthropic_messages",
                    "name": "Anthropic Messages Provider",
                    "provider": "anthropic",
                    "modes": ["chat", "tool", "runner"],
                    "capabilities": _mvp_provider_capabilities(),
                    "trust_boundary": "third-party",
                    "config_refs": [
                        "ANTHROPIC_MODEL",
                        "ANTHROPIC_BASE_URL",
                        "ANTHROPIC_VERSION",
                    ],
                    "secret_ref_names": ["ANTHROPIC_API_KEY"],
                    "budget_ref": "budget_anthropic_monthly",
                    "quota_ref": "quota_anthropic_daily",
                    "runtime_path": ANTHROPIC_PROVIDER_ADAPTER,
                    "metadata": {
                        "base_url": "https://api.anthropic.com",
                        "default_model": "claude-sonnet-4-20250514",
                        "opus_model": "claude-opus-4-1-20250805",
                        "docs_verified": "2026-05-17",
                    },
                    "docs": [
                        "docs/reference/model-providers.md",
                        "docs/reference/provider-certification.md",
                        *ANTHROPIC_OFFICIAL_DOCS,
                    ],
                    "created_at": datetime.now(UTC),
                }
            ),
            ModelProvider.model_validate(
                {
                    "id": "provider_openai_responses",
                    "name": "OpenAI Responses Provider",
                    "provider": "openai",
                    "modes": ["chat", "tool", "runner"],
                    "capabilities": _mvp_provider_capabilities(),
                    "trust_boundary": "third-party",
                    "config_refs": [
                        "OPENAI_MODEL",
                        "OPENAI_BASE_URL",
                    ],
                    "secret_ref_names": ["OPENAI_API_KEY"],
                    "budget_ref": "budget_openai_monthly",
                    "quota_ref": "quota_openai_daily",
                    "runtime_path": OPENAI_PROVIDER_ADAPTER,
                    "metadata": {
                        "base_url": "https://api.openai.com",
                        "default_model": "gpt-5.2",
                        "docs_verified": "2026-05-17",
                    },
                    "docs": [
                        "docs/reference/model-providers.md",
                        "docs/reference/provider-certification.md",
                        *OPENAI_OFFICIAL_DOCS,
                    ],
                    "created_at": datetime.now(UTC),
                }
            ),
            ModelProvider.model_validate(
                {
                    "id": "provider_openai_chat",
                    "name": "OpenAI Chat Completions Provider",
                    "provider": "chat_completions",
                    "modes": ["chat", "tool", "runner"],
                    "capabilities": _mvp_provider_capabilities(),
                    "trust_boundary": "third-party",
                    "config_refs": [
                        "OPENAI_MODEL",
                        "OPENAI_BASE_URL",
                    ],
                    "secret_ref_names": ["OPENAI_API_KEY"],
                    "budget_ref": "budget_openai_monthly",
                    "quota_ref": "quota_openai_daily",
                    "runtime_path": CHAT_COMPLETIONS_PROVIDER_ADAPTER,
                    "metadata": {
                        "base_url": "https://api.openai.com",
                        "default_model": "gpt-5.2",
                        "docs_verified": "2026-05-17",
                    },
                    "docs": [
                        "docs/reference/model-providers.md",
                        "docs/reference/provider-certification.md",
                        *OPENAI_OFFICIAL_DOCS,
                    ],
                    "created_at": datetime.now(UTC),
                }
            ),
            ModelProvider.model_validate(
                {
                    "id": "provider_local_openai_compatible",
                    "name": "Local OpenAI-Compatible Provider",
                    "provider": "chat_completions",
                    "modes": ["chat", "tool", "runner"],
                    "capabilities": _mvp_provider_capabilities(),
                    "trust_boundary": "local",
                    "config_refs": [
                        "LOCAL_OPENAI_COMPATIBLE_MODEL",
                        "LOCAL_OPENAI_COMPATIBLE_BASE_URL",
                    ],
                    "secret_ref_names": [],
                    "budget_ref": "budget_local_monthly",
                    "quota_ref": "quota_local_daily",
                    "runtime_path": CHAT_COMPLETIONS_PROVIDER_ADAPTER,
                    "metadata": {
                        "base_url": "http://localhost:11434/v1",
                        "allow_local_base_url": True,
                        "default_model": "llama3.2",
                        "docs_verified": "2026-05-17",
                    },
                    "docs": [
                        "docs/reference/model-providers.md",
                        "docs/reference/provider-certification.md",
                        *OPENAI_OFFICIAL_DOCS,
                    ],
                    "created_at": datetime.now(UTC),
                }
            ),
            provider_for_local_model_preset("ollama"),
            provider_for_local_model_preset("lm-studio"),
            provider_for_local_model_preset("vllm"),
        ]
    )


def _validate_provider_base_url(provider: ModelProvider) -> None:
    configured = provider.metadata.get("base_url")
    if not isinstance(configured, str) or not configured:
        return
    allow_local = provider.id.startswith("provider_local_") or provider.metadata.get(
        "allow_local_base_url"
    ) is True
    try:
        assert_safe_provider_url(configured, allow_local=allow_local)
    except ProviderURLSafetyError as exc:
        raise ModelProviderRegistryError(str(exc)) from exc


def _mvp_provider_capabilities() -> list[dict[str, object]]:
    return [
        {
            "name": "model.chat",
            "mode": "chat",
            "description": "Provider chat request execution.",
            "grant_required": True,
        },
        {
            "name": "model.streaming",
            "mode": "chat",
            "description": "Provider streaming response support.",
            "grant_required": True,
        },
        {
            "name": "model.tool_calls",
            "mode": "tool",
            "description": "Provider tool call support.",
            "grant_required": True,
        },
        {
            "name": "model.structured_output",
            "mode": "chat",
            "description": "Provider structured output support.",
            "grant_required": True,
        },
        {
            "name": "model.usage_metadata",
            "mode": "chat",
            "description": "Provider usage metadata normalization.",
            "grant_required": True,
        },
        {
            "name": "runner.execute",
            "mode": "runner",
            "description": "Provider-backed runner execution.",
            "grant_required": True,
        },
    ]


def provider_selection_payload(
    provider: ModelProvider,
    *,
    mode: str,
    policy_envelope_id: str | None = None,
    receipt_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return a redacted provider selection payload for operator output."""
    if mode not in provider.modes:
        supported = ", ".join(provider.modes)
        raise ValueError(
            f"provider {provider.id} does not support mode {mode!r}; supported: {supported}"
        )
    return {
        "provider_id": provider.id,
        "provider": provider.provider,
        "name": provider.name,
        "mode": mode,
        "trust_boundary": provider.trust_boundary,
        "runtime_path": provider.runtime_path,
        "config_refs": provider.config_refs,
        "secret_ref_names": provider.secret_ref_names,
        "budget_ref": provider.budget_ref,
        "quota_ref": provider.quota_ref,
        "policy_envelope_id": policy_envelope_id,
        "receipt_ids": receipt_ids or [],
        "redacted": True,
    }
