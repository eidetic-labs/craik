import pytest

from craik.runtime.auth import CredentialStatus
from craik.runtime.auth.sources import EnvVarApiKeySource
from craik.runtime.providers.provider_runtime import OPENAI_OFFICIAL_DOCS, ProviderRuntimeConfig
from craik.runtime.providers.provider_runtime_support import _provider_headers


def test_env_var_api_key_source_returns_anthropic_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")

    headers = EnvVarApiKeySource("ANTHROPIC_API_KEY").headers_for("anthropic")

    assert headers == {
        "anthropic-version": "2023-06-01",
        "x-api-key": "anthropic-secret",
    }


def test_env_var_api_key_source_returns_bearer_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")

    headers = EnvVarApiKeySource("OPENAI_API_KEY").headers_for("chat_completions")

    assert headers == {"Authorization": "Bearer openai-secret"}


def test_env_var_api_key_source_returns_gemini_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret")

    headers = EnvVarApiKeySource("GEMINI_API_KEY").headers_for("gemini")

    assert headers == {"x-goog-api-key": "gemini-secret"}


def test_env_var_api_key_source_preserves_empty_local_provider_headers() -> None:
    assert EnvVarApiKeySource("").headers_for("chat_completions") == {}
    assert EnvVarApiKeySource("").headers_for("anthropic") == {
        "anthropic-version": "2023-06-01"
    }


def test_env_var_api_key_source_status_uses_safe_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MISSING_PROVIDER_SECRET", raising=False)

    status = EnvVarApiKeySource("MISSING_PROVIDER_SECRET").status()

    assert status == CredentialStatus(
        status="rejected",
        detail="secret reference could not resolve",
    )
    assert "MISSING_PROVIDER_SECRET" not in str(status)


def test_provider_headers_delegates_to_env_var_api_key_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    config = ProviderRuntimeConfig(
        provider_id="provider_openai_chat",
        provider_family="chat_completions",
        model="gpt-5.2",
        secret_ref_name="OPENAI_API_KEY",
        docs_refs=list(OPENAI_OFFICIAL_DOCS),
    )

    assert _provider_headers(config) == {"Authorization": "Bearer openai-secret"}
