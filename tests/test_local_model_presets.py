import pytest

from craik.runtime.local_models import (
    check_local_model_health,
    list_local_model_presets,
    provider_for_local_model_preset,
    require_local_model_preset,
)
from craik.runtime.providers.provider_runtime import (
    ChatCompletionsProviderAdapter,
    adapter_for_provider,
)


def test_local_model_presets_resolve_no_secret_provider_metadata() -> None:
    preset_ids = {preset.id for preset in list_local_model_presets()}
    provider = provider_for_local_model_preset("ollama")

    assert preset_ids >= {"openai-compatible", "ollama", "lm-studio", "vllm"}
    assert provider.id == "provider_local_ollama"
    assert provider.provider == "chat_completions"
    assert provider.trust_boundary == "local"
    assert provider.secret_ref_names == []
    assert provider.metadata["base_url"] == "http://localhost:11434/v1"
    assert provider.metadata["allow_local_base_url"] is True
    assert isinstance(adapter_for_provider(provider), ChatCompletionsProviderAdapter)


def test_local_model_preset_overrides_model_and_base_url_with_url_safety() -> None:
    provider = provider_for_local_model_preset(
        "lm-studio",
        base_url="http://127.0.0.1:1234/v1",
        model="qwen-local",
    )

    assert provider.metadata["base_url"] == "http://127.0.0.1:1234/v1"
    assert provider.metadata["default_model"] == "qwen-local"
    with pytest.raises(ValueError, match="private network|HTTPS"):
        provider_for_local_model_preset("ollama", base_url="http://10.0.0.5:11434/v1")


def test_local_model_health_reports_reachable_models_without_credentials() -> None:
    health = check_local_model_health(
        "openai-compatible",
        opener=lambda _url, _timeout: {
            "object": "list",
            "data": [{"id": "llama3.2"}, {"id": "qwen2.5"}],
        },
    )

    assert health.status == "ok"
    assert health.models == ["llama3.2", "qwen2.5"]
    assert health.provider_id == "provider_local_openai_compatible"


def test_local_model_health_reports_clear_diagnostics() -> None:
    def failing_opener(_url: str, _timeout: float) -> dict[str, object]:
        raise OSError("connection refused")

    health = check_local_model_health("ollama", opener=failing_opener)

    assert health.status == "rejected"
    assert "health check failed" in health.detail
    assert health.models == []


def test_local_model_preset_unknown_id_lists_known_values() -> None:
    with pytest.raises(ValueError, match="known:"):
        require_local_model_preset("missing")
