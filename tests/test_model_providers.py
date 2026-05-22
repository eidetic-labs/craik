from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from craik.contracts.models import ModelProvider
from craik.contracts.registry import schema_model
from craik.runtime.providers.model_providers import (
    DuplicateModelProviderError,
    ModelProviderNotFoundError,
    ModelProviderRegistry,
    default_model_provider_registry,
)

NOW = datetime(2026, 5, 16, 19, 40, tzinfo=UTC)


def _provider(**overrides: object) -> ModelProvider:
    payload: dict[str, object] = {
        "schema": "craik.model_provider",
        "version": "0.1.0",
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
        "runtime_path": "craik.runtime.fixture_provider",
        "metadata": {"notes": "Fixture provider metadata only."},
        "docs": ["docs/reference/model-providers.md"],
        "created_at": NOW,
    }
    payload.update(overrides)
    return ModelProvider.model_validate(payload)


def test_model_provider_registers_schema() -> None:
    assert schema_model("craik.model_provider") is ModelProvider


def test_model_provider_separates_config_and_secret_refs() -> None:
    provider = _provider()

    assert provider.config_refs == ["CRAIK_PROVIDER_FIXTURE_MODE"]
    assert provider.secret_ref_names == ["CRAIK_PROVIDER_FIXTURE_TOKEN"]
    assert "TOKEN" not in provider.metadata


def test_model_provider_rejects_secret_like_metadata() -> None:
    with pytest.raises(ValidationError, match="secret-like"):
        _provider(metadata={"api_key": "not-allowed"})


def test_model_provider_rejects_undeclared_capability_mode() -> None:
    with pytest.raises(ValidationError, match="undeclared modes"):
        _provider(
            modes=["chat"],
            capabilities=[
                {
                    "name": "runner.execute",
                    "mode": "runner",
                    "description": "Runner execution.",
                    "grant_required": True,
                }
            ],
        )


def test_model_provider_registry_registers_and_lists_by_id() -> None:
    provider_b = _provider(id="provider_b", name="Provider B")
    provider_a = _provider(id="provider_a", name="Provider A")
    registry = ModelProviderRegistry([provider_b, provider_a])

    assert registry.get("provider_a") == provider_a
    assert registry.require("provider_b") == provider_b
    assert [provider.id for provider in registry.list()] == ["provider_a", "provider_b"]


def test_model_provider_registry_rejects_duplicate_ids() -> None:
    provider = _provider()
    registry = ModelProviderRegistry([provider])

    with pytest.raises(DuplicateModelProviderError):
        registry.register(provider)


def test_model_provider_registry_requires_known_provider() -> None:
    registry = ModelProviderRegistry()

    with pytest.raises(ModelProviderNotFoundError, match="unknown model provider"):
        registry.require("missing")


def test_default_registry_includes_certified_mvp_provider_metadata() -> None:
    registry = default_model_provider_registry()

    openai = registry.require("provider_openai")
    anthropic = registry.require("provider_anthropic")
    gemini = registry.require("provider_gemini")
    anthropic_messages = registry.require("provider_anthropic_messages")
    openai_responses = registry.require("provider_openai_responses")
    openai_chat = registry.require("provider_openai_chat")
    local_openai_compatible = registry.require("provider_local_openai_compatible")

    assert openai.provider == "openai"
    assert openai.runtime_path == "craik.runtime.providers.provider_runtime.OpenAIProviderAdapter"
    assert openai.metadata["default_model"] == "gpt-5.2"
    assert "CRAIK_OPENAI_API_KEY" in openai.secret_ref_names
    assert "model.tool_calls" in {capability.name for capability in openai.capabilities}
    assert anthropic.provider == "anthropic"
    assert anthropic.runtime_path == (
        "craik.runtime.providers.provider_runtime.AnthropicProviderAdapter"
    )
    assert anthropic.metadata["default_model"] == "claude-sonnet-4-20250514"
    assert "CRAIK_ANTHROPIC_API_KEY" in anthropic.secret_ref_names
    assert gemini.provider == "gemini"
    assert gemini.runtime_path == "craik.runtime.providers.provider_runtime.GeminiProviderAdapter"
    assert gemini.metadata["base_url"] == "https://generativelanguage.googleapis.com"
    assert gemini.metadata["default_model"] == "gemini-2.5-pro"
    assert "CRAIK_GEMINI_API_KEY" in gemini.secret_ref_names
    assert anthropic_messages.provider == "anthropic"
    assert anthropic_messages.metadata["base_url"] == "https://api.anthropic.com"
    assert anthropic_messages.metadata["default_model"] == "claude-sonnet-4-20250514"
    assert anthropic_messages.metadata["opus_model"] == "claude-opus-4-1-20250805"
    assert anthropic_messages.secret_ref_names == ["ANTHROPIC_API_KEY"]
    assert openai_responses.provider == "openai"
    assert openai_responses.runtime_path == (
        "craik.runtime.providers.provider_runtime.OpenAIProviderAdapter"
    )
    assert openai_responses.metadata["base_url"] == "https://api.openai.com"
    assert openai_responses.secret_ref_names == ["OPENAI_API_KEY"]
    assert openai_chat.provider == "chat_completions"
    assert openai_chat.runtime_path == (
        "craik.runtime.providers.provider_runtime.ChatCompletionsProviderAdapter"
    )
    assert openai_chat.metadata["base_url"] == "https://api.openai.com"
    assert openai_chat.secret_ref_names == ["OPENAI_API_KEY"]
    assert local_openai_compatible.provider == "chat_completions"
    assert local_openai_compatible.trust_boundary == "local"
    assert local_openai_compatible.metadata["base_url"] == "http://localhost:11434/v1"
    assert local_openai_compatible.secret_ref_names == []
