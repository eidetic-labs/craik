from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from craik.contracts.models import (
    CompiledPrompt,
    ModelProvider,
    PolicyEnvelope,
    RunnerMetadata,
    RunnerStepRequest,
)
from craik.runtime.auth import (
    AuthProfile,
    AuthProfileStore,
    CredentialKind,
    CredentialPool,
    CredentialPoolConfig,
    CredentialPoolEntry,
)
from craik.runtime.auth.guided_setup import default_pool_for_profile
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.paths import ensure_craik_home
from craik.runtime.providers.model_providers import default_model_provider_registry
from craik.runtime.providers.provider_runner import ProviderBackedStepRunner
from craik.runtime.providers.provider_runtime import (
    ANTHROPIC_OFFICIAL_DOCS,
    GEMINI_OFFICIAL_DOCS,
    OPENAI_OFFICIAL_DOCS,
    AnthropicProviderAdapter,
    ChatCompletionsProviderAdapter,
    CredentialApprovalRequiredError,
    GeminiProviderAdapter,
    OpenAIProviderAdapter,
    ProviderLiveAccessNotConfiguredError,
    ProviderMessage,
    ProviderRuntimeAdapter,
    ProviderRuntimeConfig,
    ProviderRuntimeError,
    ProviderRuntimeRequest,
    ProviderTool,
    adapter_for_provider,
    provider_runtime_receipt,
)
from craik.runtime.providers.provider_runtime_support import _provider_headers
from craik.runtime.providers.provider_transport import (
    FixtureTransport,
    ProviderFamily,
    ProviderTransport,
)
from craik.runtime.secrets import SecretResolver
from craik.runtime.shell.credential_storage import StoredCredential
from craik.runtime.store import LocalStore


def test_provider_runtime_keeps_extracted_import_surface() -> None:
    from craik.runtime.providers.provider_config import (
        ProviderRuntimeConfig as extracted_config,
    )
    from craik.runtime.providers.provider_models import (
        CredentialApprovalRequiredError as extracted_approval_error,
    )
    from craik.runtime.providers.provider_models import ProviderMessage as extracted_message
    from craik.runtime.providers.provider_models import (
        ProviderMessageRole as extracted_message_role,
    )
    from craik.runtime.providers.provider_models import (
        ProviderRuntimeError as extracted_runtime_error,
    )
    from craik.runtime.providers.provider_models import (
        ProviderRuntimeRequest as extracted_request,
    )
    from craik.runtime.providers.provider_runtime import (
        CredentialApprovalRequiredError as runtime_approval_error,
    )
    from craik.runtime.providers.provider_runtime import ProviderMessage as runtime_message
    from craik.runtime.providers.provider_runtime import (
        ProviderMessageRole as runtime_message_role,
    )
    from craik.runtime.providers.provider_runtime import (
        ProviderRuntimeConfig as runtime_config,
    )
    from craik.runtime.providers.provider_runtime import (
        ProviderRuntimeError as runtime_error,
    )
    from craik.runtime.providers.provider_runtime import (
        ProviderRuntimeRequest as runtime_request,
    )
    from craik.runtime.providers.provider_runtime import (
        provider_runtime_receipt as runtime_receipt,
    )
    from craik.runtime.providers.provider_runtime_support import (
        provider_runtime_receipt as extracted_receipt,
    )

    assert runtime_config is extracted_config
    assert runtime_message is extracted_message
    assert runtime_message_role is extracted_message_role
    assert runtime_request is extracted_request
    assert runtime_error is extracted_runtime_error
    assert runtime_approval_error is extracted_approval_error
    assert runtime_receipt is extracted_receipt


def test_provider_runtime_adapter_protocol_defaults_raise_not_implemented() -> None:
    class IncompleteProviderRuntimeAdapter(ProviderRuntimeAdapter):
        pass

    adapter = IncompleteProviderRuntimeAdapter()
    request = ProviderRuntimeRequest(messages=[ProviderMessage(role="user", content="hi")])

    with pytest.raises(NotImplementedError):
        adapter.execute(request)
    with pytest.raises(NotImplementedError):
        adapter.build_payload(request)
    with pytest.raises(NotImplementedError):
        adapter.normalize_response({})
    with pytest.raises(NotImplementedError):
        adapter.classify_error(status_code=None)
    with pytest.raises(NotImplementedError):
        adapter.require_live_access()


def _openai_adapter(*, live_enabled: bool = False) -> OpenAIProviderAdapter:
    return OpenAIProviderAdapter(
        ProviderRuntimeConfig(
            provider_id="provider_openai",
            provider_family="openai",
            model="gpt-5.2",
            secret_ref_name="CRAIK_OPENAI_API_KEY",
            live_enabled=live_enabled,
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
        )
    )


def _anthropic_adapter(*, live_enabled: bool = False) -> AnthropicProviderAdapter:
    return AnthropicProviderAdapter(
        ProviderRuntimeConfig(
            provider_id="provider_anthropic",
            provider_family="anthropic",
            model="claude-sonnet-4-20250514",
            secret_ref_name="CRAIK_ANTHROPIC_API_KEY",
            live_enabled=live_enabled,
            docs_refs=list(ANTHROPIC_OFFICIAL_DOCS),
        )
    )


def _chat_completions_adapter(
    *, live_enabled: bool = False
) -> ChatCompletionsProviderAdapter:
    return ChatCompletionsProviderAdapter(
        ProviderRuntimeConfig(
            provider_id="provider_openai_chat",
            provider_family="chat_completions",
            model="gpt-5.2",
            secret_ref_name="CRAIK_OPENAI_API_KEY",
            live_enabled=live_enabled,
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
        )
    )


def _gemini_adapter(*, live_enabled: bool = False) -> GeminiProviderAdapter:
    return GeminiProviderAdapter(
        ProviderRuntimeConfig(
            provider_id="provider_gemini",
            provider_family="gemini",
            model="gemini-2.5-pro",
            secret_ref_name="CRAIK_GEMINI_API_KEY",
            live_enabled=live_enabled,
            docs_refs=list(GEMINI_OFFICIAL_DOCS),
        )
    )


def _request() -> ProviderRuntimeRequest:
    return ProviderRuntimeRequest(
        messages=[
            ProviderMessage(role="system", content="Follow the policy."),
            ProviderMessage(role="user", content="Create a plan."),
        ],
        tools=[
            ProviderTool(
                name="lookup_case",
                description="Lookup case metadata.",
                input_schema={
                    "type": "object",
                    "properties": {"case_id": {"type": "string"}},
                    "required": ["case_id"],
                },
            )
        ],
        structured_output_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        },
        stream=True,
        metadata={"user_id": "case-user", "api_key": "craik-test-not-a-real-key-01"},
    )


def test_openai_payload_supports_messages_tools_structured_output_and_redaction() -> None:
    payload = _openai_adapter().build_payload(_request())

    assert payload["model"] == "gpt-5.2"
    assert payload["stream"] is True
    assert payload["input"][0] == {"role": "developer", "content": "Follow the policy."}
    assert payload["tools"][0]["type"] == "function"
    assert payload["tools"][0]["strict"] is True
    assert payload["tool_choice"] == "auto"
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["strict"] is True
    assert payload["metadata"]["api_key"] == "[REDACTED]"


def test_openai_response_normalizes_text_tool_calls_usage_and_retry_decisions() -> None:
    adapter = _openai_adapter()
    result = adapter.normalize_response(
        {
            "id": "resp_123",
            "model": "gpt-5.2",
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": "Done"}]},
                {
                    "type": "function_call",
                    "id": "fc_123",
                    "call_id": "call_123",
                    "name": "lookup_case",
                    "arguments": '{"token":"Bearer craiktestnotarealkey01"}',
                },
            ],
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        }
    )
    retryable = adapter.classify_error(status_code=429, headers={"retry-after": "7"})
    terminal = adapter.classify_error(status_code=400)

    assert result.text == "Done"
    assert result.tool_calls[0]["arguments"] == '{"token":"Bearer [REDACTED]"}'
    assert result.usage == {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
    assert retryable.retryable is True
    assert retryable.retry_after_seconds == 7
    assert terminal.retryable is False


def test_anthropic_payload_supports_messages_tools_structured_output_and_secret_refs() -> None:
    payload = _anthropic_adapter().build_payload(_request())

    assert payload["model"] == "claude-sonnet-4-20250514"
    assert payload["stream"] is True
    assert payload["system"] == "Follow the policy."
    assert payload["messages"] == [{"role": "user", "content": "Create a plan."}]
    assert payload["tools"][0]["name"] == "lookup_case"
    assert payload["tools"][0]["input_schema"]["required"] == ["case_id"]
    assert payload["tools"][1]["name"] == "craik_structured_output"
    assert payload["tool_choice"] == {"type": "tool", "name": "craik_structured_output"}
    assert payload["metadata"] == {"user_id": "case-user"}


def test_anthropic_response_normalizes_text_tool_calls_usage_and_retry_decisions() -> None:
    adapter = _anthropic_adapter()
    result = adapter.normalize_response(
        {
            "id": "msg_123",
            "model": "claude-sonnet-4-20250514",
            "content": [
                {"type": "text", "text": "Done"},
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "craik_structured_output",
                    "input": {"answer": "ok", "token": "craik-test-not-a-real-key-01"},
                },
            ],
            "usage": {"input_tokens": 11, "output_tokens": 6},
        }
    )
    retryable = adapter.classify_error(status_code=529, headers={"Retry-After": "11"})
    terminal = adapter.classify_error(status_code=400)

    assert result.text == "Done"
    assert result.structured_output == {"answer": "ok", "token": "craik-test-not-a-real-key-01"}
    assert result.tool_calls[0]["input"] == {"answer": "ok", "token": "[REDACTED]"}
    assert result.usage == {"input_tokens": 11, "output_tokens": 6, "total_tokens": 17}
    assert retryable.retryable is True
    assert retryable.retry_after_seconds == 11
    assert terminal.retryable is False


def test_chat_completions_payload_supports_messages_tools_and_structured_output() -> None:
    payload = _chat_completions_adapter().build_payload(_request())

    assert payload["model"] == "gpt-5.2"
    assert payload["stream"] is True
    assert payload["max_tokens"] == 1024
    assert payload["messages"][0] == {"role": "system", "content": "Follow the policy."}
    assert payload["tools"][0] == {
        "type": "function",
        "function": {
            "name": "lookup_case",
            "description": "Lookup case metadata.",
            "parameters": {
                "type": "object",
                "properties": {"case_id": {"type": "string"}},
                "required": ["case_id"],
            },
        },
    }
    assert payload["tool_choice"] == "auto"
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True


def test_chat_completions_payload_omits_tools_and_structured_output_when_absent() -> None:
    request = ProviderRuntimeRequest(
        messages=[ProviderMessage(role="user", content="Create a plan.")],
    )

    payload = _chat_completions_adapter().build_payload(request)

    assert payload["messages"] == [{"role": "user", "content": "Create a plan."}]
    assert "tools" not in payload
    assert "response_format" not in payload


def test_chat_completions_response_normalizes_content_tool_calls_usage() -> None:
    adapter = _chat_completions_adapter()
    content = adapter.normalize_response(
        {
            "id": "chatcmpl_123",
            "model": "gpt-5.2",
            "choices": [{"message": {"role": "assistant", "content": "Done"}}],
            "usage": {
                "prompt_tokens": 13,
                "completion_tokens": 8,
                "total_tokens": 21,
            },
        }
    )
    tool_call = adapter.normalize_response(
        {
            "id": "chatcmpl_456",
            "model": "gpt-5.2",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"answer":"ok"}',
                        "tool_calls": [
                            {
                                "id": "call_123",
                                "type": "function",
                                "function": {
                                    "name": "lookup_case",
                                    "arguments": '{"token":"Bearer craiktestnotarealkey01"}',
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        }
    )
    retryable = adapter.classify_error(status_code=429, headers={"Retry-After": "9"})
    server_error = adapter.classify_error(status_code=503)
    terminal = adapter.classify_error(status_code=400)

    assert content.text == "Done"
    assert content.usage == {"input_tokens": 13, "output_tokens": 8, "total_tokens": 21}
    assert tool_call.structured_output == {"answer": "ok"}
    assert tool_call.tool_calls == [
        {
            "id": "call_123",
            "type": "function",
            "name": "lookup_case",
            "arguments": '{"token":"Bearer [REDACTED]"}',
        }
    ]
    assert tool_call.usage == {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8}
    assert retryable.retryable is True
    assert retryable.retry_after_seconds == 9
    assert server_error.retryable is True
    assert terminal.retryable is False


def test_gemini_payload_supports_messages_tools_structured_output_and_system_instruction() -> None:
    payload = _gemini_adapter().build_payload(_request())

    assert payload["_path"] == "/v1beta/models/gemini-2.5-pro:streamGenerateContent?alt=sse"
    assert payload["systemInstruction"] == {"parts": [{"text": "Follow the policy."}]}
    assert payload["contents"] == [
        {"role": "user", "parts": [{"text": "Create a plan."}]}
    ]
    assert payload["tools"][0]["functionDeclarations"][0]["name"] == "lookup_case"
    assert payload["tools"][0]["functionDeclarations"][0]["parameters"]["required"] == [
        "case_id"
    ]
    assert payload["toolConfig"] == {"functionCallingConfig": {"mode": "AUTO"}}
    assert payload["generationConfig"]["maxOutputTokens"] == 1024
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert payload["generationConfig"]["responseSchema"]["required"] == ["answer"]


def test_gemini_response_normalizes_text_tool_calls_usage_and_retry_decisions() -> None:
    adapter = _gemini_adapter()
    result = adapter.normalize_response(
        {
            "responseId": "gemini_resp_123",
            "modelVersion": "gemini-2.5-pro",
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {"text": '{"answer":"ok"}'},
                            {
                                "functionCall": {
                                    "name": "lookup_case",
                                    "args": {
                                        "token": "craik-test-not-a-real-key-01",
                                        "case_id": "case_1",
                                    },
                                }
                            },
                        ],
                    }
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 12,
                "candidatesTokenCount": 7,
                "totalTokenCount": 19,
            },
        }
    )
    retryable = adapter.classify_error(status_code=503, headers={"Retry-After": "5"})
    throttled = adapter.classify_error(status_code=429)
    terminal = adapter.classify_error(status_code=400)

    assert result.text == '{"answer":"ok"}'
    assert result.structured_output == {"answer": "ok"}
    assert result.tool_calls == [
        {
            "name": "lookup_case",
            "arguments": {"token": "[REDACTED]", "case_id": "case_1"},
        }
    ]
    assert result.usage == {"input_tokens": 12, "output_tokens": 7, "total_tokens": 19}
    assert result.response_id == "gemini_resp_123"
    assert retryable.retryable is True
    assert retryable.retry_after_seconds == 5
    assert throttled.retryable is True
    assert terminal.retryable is False


def test_chat_completions_stream_chunk_normalizes_delta_content_and_tool_calls() -> None:
    chunk = _chat_completions_adapter().normalize_chunk(
        {
            "id": "chatcmpl_chunk",
            "model": "gpt-5.2",
            "choices": [
                {
                    "delta": {
                        "content": "Hel",
                        "tool_calls": [
                            {
                                "id": "call_123",
                                "type": "function",
                                "function": {
                                    "name": "lookup_case",
                                    "arguments": '{"case_id":"case_1"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": None,
                }
            ],
        }
    )

    assert chunk.text_delta == "Hel"
    assert chunk.tool_calls[0]["name"] == "lookup_case"
    assert chunk.response_id == "chatcmpl_chunk"


def test_chat_completions_stream_execute_emits_callback_chunks() -> None:
    chunks: list[str] = []
    adapter = ChatCompletionsProviderAdapter(
        _chat_completions_adapter().config,
        transport=FixtureTransport(
            family="chat_completions",
            model="gpt-5.2",
            response_id="chatcmpl_stream_fixture",
            stream_chunks=("Hel", "lo", "!"),
        ),
    )

    result = adapter.execute(
        ProviderRuntimeRequest(
            messages=[ProviderMessage(role="user", content="Say hello.")],
            stream=True,
        ),
        stream_callback=chunks.append,
    )

    assert chunks == ["Hel", "lo", "!"]
    assert result.text == "Hello!"
    assert result.response_id == "chatcmpl_stream_fixture"
    assert result.usage == {"input_tokens": 20, "output_tokens": 3, "total_tokens": 23}


def test_live_provider_access_requires_explicit_enablement() -> None:
    with pytest.raises(ProviderLiveAccessNotConfiguredError):
        _openai_adapter().require_live_access()
    with pytest.raises(ProviderLiveAccessNotConfiguredError):
        _anthropic_adapter().require_live_access()
    with pytest.raises(ProviderLiveAccessNotConfiguredError):
        _gemini_adapter().require_live_access()
    with pytest.raises(ProviderLiveAccessNotConfiguredError):
        _chat_completions_adapter().require_live_access()

    _openai_adapter(live_enabled=True).require_live_access()
    _anthropic_adapter(live_enabled=True).require_live_access()
    _gemini_adapter(live_enabled=True).require_live_access()
    _chat_completions_adapter(live_enabled=True).require_live_access()


@pytest.mark.parametrize(
    ("adapter", "family"),
    [
        (_openai_adapter(), "openai"),
        (_anthropic_adapter(), "anthropic"),
        (_gemini_adapter(), "gemini"),
    ],
)
def test_fixture_transport_yields_provider_family_response(
    adapter: OpenAIProviderAdapter | AnthropicProviderAdapter | GeminiProviderAdapter,
    family: ProviderFamily,
) -> None:
    transport: ProviderTransport = FixtureTransport(
        family=family,
        model=adapter.config.model,
        response_id="provider_response_fixture_plan",
        phase="plan",
        status="completed",
    )

    chunks = list(transport.send(adapter.build_payload(_request()), stream=False))
    result = adapter.normalize_response(chunks[0])

    assert len(chunks) == 1
    assert result.response_id == "provider_response_fixture_plan"
    assert result.model == adapter.config.model
    assert result.text == f"{family} fixture completed plan with status completed."


def test_adapter_for_default_mvp_providers_uses_verified_docs_and_secret_references() -> None:
    registry = default_model_provider_registry()

    openai = adapter_for_provider(registry.require("provider_openai"))
    anthropic = adapter_for_provider(registry.require("provider_anthropic"))
    gemini = adapter_for_provider(registry.require("provider_gemini"))
    openai_responses = adapter_for_provider(registry.require("provider_openai_responses"))
    anthropic_messages = adapter_for_provider(
        registry.require("provider_anthropic_messages")
    )
    openai_chat = adapter_for_provider(registry.require("provider_openai_chat"))
    local_openai_compatible = adapter_for_provider(
        registry.require("provider_local_openai_compatible")
    )

    assert isinstance(openai, OpenAIProviderAdapter)
    assert openai.config.secret_ref_name == "CRAIK_OPENAI_API_KEY"
    assert openai.config.docs_refs == list(OPENAI_OFFICIAL_DOCS)
    assert isinstance(anthropic, AnthropicProviderAdapter)
    assert anthropic.config.secret_ref_name == "CRAIK_ANTHROPIC_API_KEY"
    assert anthropic.config.docs_refs == list(ANTHROPIC_OFFICIAL_DOCS)
    assert isinstance(gemini, GeminiProviderAdapter)
    assert gemini.config.secret_ref_name == "CRAIK_GEMINI_API_KEY"
    assert gemini.config.base_url == "https://generativelanguage.googleapis.com"
    assert gemini.config.docs_refs == list(GEMINI_OFFICIAL_DOCS)
    assert isinstance(openai_responses, OpenAIProviderAdapter)
    assert openai_responses.config.secret_ref_name == "OPENAI_API_KEY"
    assert openai_responses.config.base_url == "https://api.openai.com"
    assert isinstance(anthropic_messages, AnthropicProviderAdapter)
    assert anthropic_messages.config.secret_ref_name == "ANTHROPIC_API_KEY"
    assert anthropic_messages.config.base_url == "https://api.anthropic.com"
    assert isinstance(openai_chat, ChatCompletionsProviderAdapter)
    assert openai_chat.config.secret_ref_name == "OPENAI_API_KEY"
    assert openai_chat.config.base_url == "https://api.openai.com"
    assert isinstance(local_openai_compatible, ChatCompletionsProviderAdapter)
    assert local_openai_compatible.config.secret_ref_name == ""
    assert local_openai_compatible.config.base_url == "http://localhost:11434/v1"


def test_adapter_for_live_provider_uses_default_credential_pool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRAIK_HOME", str(tmp_path))
    profile = AuthProfile(
        id="anthropic:default",
        kind=CredentialKind.KEYRING_REF,
        provider_family="anthropic",
        metadata={
            "ref": "anthropic:default:claude-cli-token",
            "credential_mode": "claude-cli",
        },
        created_at=datetime(2026, 5, 17, tzinfo=UTC),
    )
    AuthProfileStore(tmp_path).put(profile)
    CredentialPool(tmp_path).put(default_pool_for_profile(profile))
    monkeypatch.setattr(
        "craik.runtime.auth.sources.keyring_ref.get_cached_credential",
        lambda ref: StoredCredential(
            value="sk-ant-oat01-test-token",
            backend="test",
            secure=True,
        ),
    )

    adapter = adapter_for_provider(
        default_model_provider_registry().require("provider_anthropic"),
        live_enabled=True,
    )

    assert adapter.config.credential_pool_id == "anthropic:default"
    assert adapter.config.secret_ref_name == "CRAIK_ANTHROPIC_API_KEY"
    headers = _provider_headers(adapter.config)
    assert headers["Authorization"] == "Bearer sk-ant-oat01-test-token"
    assert headers["anthropic-beta"] == "claude-code-20250219,oauth-2025-04-20"
    assert "x-api-key" not in headers
    assert adapter.config.last_auth_profile_id == "anthropic:default"


def test_adapter_for_provider_dispatches_chat_completions_family() -> None:
    provider = ModelProvider.model_validate(
        {
            "id": "provider_openai_chat",
            "name": "OpenAI Chat Completions",
            "provider": "chat_completions",
            "modes": ["chat", "tool", "runner"],
            "capabilities": [
                {
                    "name": "model.chat",
                    "mode": "chat",
                    "description": "Chat completions request execution.",
                    "grant_required": True,
                }
            ],
            "trust_boundary": "third-party",
            "config_refs": ["OPENAI_BASE_URL"],
            "secret_ref_names": ["OPENAI_API_KEY"],
            "budget_ref": "budget_openai_monthly",
            "quota_ref": "quota_openai_daily",
            "runtime_path": (
                "craik.runtime.providers.provider_runtime.ChatCompletionsProviderAdapter"
            ),
            "metadata": {
                "default_model": "gpt-5.2",
                "docs_verified": "2026-05-17",
            },
            "docs": ["docs/reference/model-providers.md", *OPENAI_OFFICIAL_DOCS],
            "created_at": "2026-05-17T08:00:00Z",
        }
    )

    adapter = adapter_for_provider(provider)

    assert isinstance(adapter, ChatCompletionsProviderAdapter)
    assert adapter.config.provider_family == "chat_completions"
    assert adapter.config.secret_ref_name == "OPENAI_API_KEY"


def test_provider_runtime_rejects_raw_secret_config_and_missing_docs() -> None:
    with pytest.raises(ValidationError, match="raw secret material"):
        ProviderRuntimeConfig(
            provider_id="provider_openai",
            provider_family="openai",
            model="gpt-5.2",
            secret_ref_name="token=craik-test-not-a-real-key-raw",
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
        )


def test_provider_runtime_rejects_profile_and_pool_together() -> None:
    with pytest.raises(ValidationError, match="mutually exclusive"):
        ProviderRuntimeConfig(
            provider_id="provider_openai",
            provider_family="openai",
            model="gpt-5.2",
            secret_ref_name="OPENAI_API_KEY",
            auth_profile_id="openai:work",
            credential_pool_id="openai:default",
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
        )
    with pytest.raises(ValidationError, match="missing official refs"):
        ProviderRuntimeConfig(
            provider_id="provider_openai",
            provider_family="openai",
            model="gpt-5.2",
            secret_ref_name="CRAIK_OPENAI_API_KEY",
            docs_refs=["docs/reference/model-providers.md"],
        )


def test_provider_runtime_config_allows_no_secret_for_local_providers() -> None:
    config = ProviderRuntimeConfig(
        provider_id="provider_local_openai_compatible",
        provider_family="chat_completions",
        model="llama3.2",
        secret_ref_name="",
        docs_refs=list(OPENAI_OFFICIAL_DOCS),
    )

    assert config.resolve_secret(SecretResolver()) == ""


def test_provider_runtime_config_resolves_secret_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRAIK_OPENAI_API_KEY", "resolved-secret")

    assert _openai_adapter().config.resolve_secret(SecretResolver()) == "resolved-secret"


def test_provider_headers_use_gemini_api_key_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRAIK_GEMINI_API_KEY", "gemini-secret")

    assert _provider_headers(_gemini_adapter().config) == {"x-goog-api-key": "gemini-secret"}


def test_provider_headers_resolve_auth_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRAIK_HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "profile-secret")
    AuthProfileStore(tmp_path).put(
        AuthProfile(
            id="openai:work",
            kind=CredentialKind.API_KEY,
            provider_family="openai",
            metadata={"env_var": "OPENAI_API_KEY"},
            created_at=datetime(2026, 5, 17, tzinfo=UTC),
        )
    )
    config = ProviderRuntimeConfig(
        provider_id="provider_openai",
        provider_family="openai",
        model="gpt-5.2",
        secret_ref_name="",
        auth_profile_id="openai:work",
        docs_refs=list(OPENAI_OFFICIAL_DOCS),
    )

    assert _provider_headers(config) == {"Authorization": "Bearer profile-secret"}
    assert config.last_auth_profile_id == "openai:work"


def test_provider_headers_resolve_credential_pool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRAIK_HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "pool-secret")
    AuthProfileStore(tmp_path).put(
        AuthProfile(
            id="openai:pool",
            kind=CredentialKind.API_KEY,
            provider_family="openai",
            metadata={"env_var": "OPENAI_API_KEY"},
            created_at=datetime(2026, 5, 17, tzinfo=UTC),
        )
    )
    CredentialPool(tmp_path).put(
        CredentialPoolConfig(
            id="openai:default",
            provider_family="openai",
            profiles=[CredentialPoolEntry(profile_id="openai:pool")],
        )
    )
    config = ProviderRuntimeConfig(
        provider_id="provider_openai",
        provider_family="openai",
        model="gpt-5.2",
        secret_ref_name="",
        credential_pool_id="openai:default",
        docs_refs=list(OPENAI_OFFICIAL_DOCS),
    )

    assert _provider_headers(config) == {"Authorization": "Bearer pool-secret"}
    assert config.last_auth_profile_id == "openai:pool"


def test_provider_runtime_receipt_keeps_safe_metadata_and_drops_payload_and_secret_ref() -> None:
    adapter = _openai_adapter()
    request = _request()
    result = adapter.normalize_response(
        {
            "id": "resp_123",
            "model": "gpt-5.2",
            "output_text": "Done",
            "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
        }
    )

    receipt = provider_runtime_receipt(
        adapter=adapter,
        request=request,
        result=result,
        task_id="task_provider_runtime",
        policy_envelope_id="policy_provider_runtime",
        receipt_id="receipt_provider_runtime",
        actor="agent:codex",
    )

    assert receipt.target == "provider_action:provider_openai"
    assert receipt.result.metadata["provider_family"] == "openai"
    assert receipt.result.metadata["usage"] == {
        "input": 3,
        "output": 2,
        "total": 5,
    }
    assert receipt.result.metadata["tool_call_count"] == 0
    assert "payload" not in receipt.result.metadata
    assert "secret_ref_name" not in receipt.result.metadata
    assert receipt.auth_profile_id == "openai:legacy-env"
    assert receipt.auth_kind == "api-key"
    assert receipt.auth_identity_hash


def test_provider_runtime_receipt_records_no_credential_marker_identity() -> None:
    adapter = OpenAIProviderAdapter(
        ProviderRuntimeConfig(
            provider_id="provider_openai_local",
            provider_family="openai",
            model="gpt-5.2",
            secret_ref_name="",
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
        )
    )
    request = _request()
    result = adapter.normalize_response(
        {
            "id": "resp_marker",
            "model": "gpt-5.2",
            "output_text": "Done",
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }
    )

    receipt = provider_runtime_receipt(
        adapter=adapter,
        request=request,
        result=result,
        task_id="task_provider_runtime",
        policy_envelope_id="policy_provider_runtime",
        receipt_id="receipt_provider_runtime_marker",
        actor="agent:codex",
    )

    assert receipt.auth_profile_id == "openai:no-credential"
    assert receipt.auth_kind == "marker"
    assert receipt.auth_identity_hash


def test_provider_runtime_receipt_records_auth_profile_identity_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRAIK_HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_WORK_KEY", "token=craik-test-not-a-real-key-raw")
    AuthProfileStore(tmp_path).put(
        AuthProfile(
            id="openai:work",
            kind=CredentialKind.API_KEY,
            provider_family="openai",
            metadata={"env_var": "OPENAI_WORK_KEY"},
            created_at=datetime(2026, 5, 17, tzinfo=UTC),
        )
    )
    adapter = OpenAIProviderAdapter(
        ProviderRuntimeConfig(
            provider_id="provider_openai",
            provider_family="openai",
            model="gpt-5.2",
            secret_ref_name="",
            auth_profile_id="openai:work",
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
        )
    )
    _provider_headers(adapter.config)
    request = ProviderRuntimeRequest(messages=[ProviderMessage(role="user", content="hi")])
    result = adapter.normalize_response(
        {
            "id": "resp_123",
            "model": "gpt-5.2",
            "output_text": "Done",
        }
    )

    first = provider_runtime_receipt(
        adapter=adapter,
        request=request,
        result=result,
        task_id="task_provider_runtime",
        policy_envelope_id="policy_provider_runtime",
        receipt_id="receipt_provider_runtime",
        actor="agent:codex",
    )
    second = provider_runtime_receipt(
        adapter=adapter,
        request=request,
        result=result,
        task_id="task_provider_runtime",
        policy_envelope_id="policy_provider_runtime",
        receipt_id="receipt_provider_runtime_2",
        actor="agent:codex",
    )

    assert first.auth_profile_id == "openai:work"
    assert first.auth_kind == "api-key"
    assert first.auth_identity_hash == second.auth_identity_hash
    assert "token=craik-test-not-a-real-key-raw" not in first.model_dump_json()
    assert "OPENAI_WORK_KEY" not in first.auth_identity_hash


def test_provider_runtime_receipt_applies_auth_profile_redaction_patterns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRAIK_HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_WORK_KEY", "token=craik-test-not-a-real-key-raw")
    AuthProfileStore(tmp_path).put(
        AuthProfile(
            id="openai:work",
            kind=CredentialKind.API_KEY,
            provider_family="openai",
            metadata={"env_var": "OPENAI_WORK_KEY"},
            redaction_patterns=[r"work-account@example\.test", "org-secret-123"],
            created_at=datetime(2026, 5, 17, tzinfo=UTC),
        )
    )
    adapter = OpenAIProviderAdapter(
        ProviderRuntimeConfig(
            provider_id="provider_openai",
            provider_family="openai",
            model="gpt-5.2",
            secret_ref_name="",
            auth_profile_id="openai:work",
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
        )
    )
    _provider_headers(adapter.config)
    request = ProviderRuntimeRequest(
        messages=[ProviderMessage(role="user", content="hi")],
        metadata={
            "operator_subject": "operator-123",
            "operator_issuer": "https://issuer.example.test",
            "operator_email": "work-account@example.test",
        },
    )
    result = adapter.normalize_response(
        {
            "id": "resp_123",
            "model": "org-secret-123-model",
            "output_text": "Done",
        }
    )

    receipt = provider_runtime_receipt(
        adapter=adapter,
        request=request,
        result=result,
        task_id="task_provider_runtime",
        policy_envelope_id="policy_provider_runtime",
        receipt_id="receipt_provider_runtime",
        actor="agent:codex",
    )
    dumped = receipt.model_dump_json()

    assert "work-account@example.test" not in dumped
    assert "org-secret-123" not in dumped
    assert receipt.operator_email == "[REDACTED]"
    assert receipt.result.metadata["model"] == "[REDACTED]-model"
    assert "token=craik-test-not-a-real-key-raw" not in dumped


def test_provider_runtime_receipt_does_not_apply_other_profile_redaction_patterns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRAIK_HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_OTHER_KEY", "token=craik-test-not-a-real-key-raw")
    AuthProfileStore(tmp_path).put(
        AuthProfile(
            id="openai:other",
            kind=CredentialKind.API_KEY,
            provider_family="openai",
            metadata={"env_var": "OPENAI_OTHER_KEY"},
            created_at=datetime(2026, 5, 17, tzinfo=UTC),
        )
    )
    adapter = OpenAIProviderAdapter(
        ProviderRuntimeConfig(
            provider_id="provider_openai",
            provider_family="openai",
            model="gpt-5.2",
            secret_ref_name="",
            auth_profile_id="openai:other",
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
        )
    )
    _provider_headers(adapter.config)
    request = ProviderRuntimeRequest(
        messages=[ProviderMessage(role="user", content="hi")],
        metadata={
            "operator_subject": "operator-123",
            "operator_issuer": "https://issuer.example.test",
            "operator_email": "work-account@example.test",
        },
    )
    result = adapter.normalize_response(
        {
            "id": "resp_123",
            "model": "org-secret-123-model",
            "output_text": "Done",
        }
    )

    receipt = provider_runtime_receipt(
        adapter=adapter,
        request=request,
        result=result,
        task_id="task_provider_runtime",
        policy_envelope_id="policy_provider_runtime",
        receipt_id="receipt_provider_runtime",
        actor="agent:codex",
    )

    assert receipt.operator_email == "work-account@example.test"
    assert receipt.result.metadata["model"] == "org-secret-123-model"
    assert "token=craik-test-not-a-real-key-raw" not in receipt.model_dump_json()


def test_provider_request_requires_operator_identity_before_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRAIK_HOME", str(tmp_path / "home"))
    transport = _CountingTransport()
    adapter = OpenAIProviderAdapter(
        ProviderRuntimeConfig(
            provider_id="provider_openai",
            provider_family="openai",
            model="gpt-5.2",
            secret_ref_name="",
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
        ),
        transport=transport,
    )
    request = ProviderRuntimeRequest(
        messages=[ProviderMessage(role="user", content="hi")],
        metadata={"operator_identity_required": True},
    )

    with pytest.raises(ProviderRuntimeError, match="run craik login"):
        adapter.execute(request)

    assert transport.calls == 0


def test_provider_request_binds_active_operator_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    monkeypatch.setenv("CRAIK_HOME", str(paths.home))
    OperatorSessionStore(paths.home).put(
        OperatorSession(
            subject="operator-123",
            email="operator@example.test",
            display_name="Operator",
            groups=["platform"],
            issuer="https://issuer.example.test",
            id_token_jti="token-1",
            expires_at=datetime(2026, 5, 18, tzinfo=UTC),
        )
    )
    adapter = _openai_adapter()
    request = ProviderRuntimeRequest(messages=[ProviderMessage(role="user", content="hi")])
    result = adapter.execute(request)

    receipt = provider_runtime_receipt(
        adapter=adapter,
        request=request,
        result=result,
        task_id="task_provider_runtime",
        policy_envelope_id="policy_provider_runtime",
        receipt_id="receipt_provider_runtime",
        actor="agent:codex",
    )

    assert request.metadata["operator_subject"] == "operator-123"
    assert request.metadata["operator_issuer"] == "https://issuer.example.test"
    assert receipt.operator_subject == "operator-123"
    assert receipt.operator_issuer == "https://issuer.example.test"
    assert receipt.operator_email == "operator@example.test"
    assert receipt.operator_groups == ["platform"]
    assert receipt.result.metadata["operator_subject"] == "operator-123"
    assert receipt.result.metadata["operator_groups"] == ["platform"]


def test_provider_request_enforces_operator_policy_before_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    monkeypatch.setenv("CRAIK_HOME", str(paths.home))
    OperatorSessionStore(paths.home).put(
        OperatorSession(
            subject="operator-123",
            email="operator@example.test",
            display_name="Operator",
            groups=["platform"],
            issuer="https://issuer.example.test",
            id_token_jti="token-1",
            expires_at=datetime(2026, 5, 18, tzinfo=UTC),
        )
    )
    transport = _CountingTransport()
    adapter = OpenAIProviderAdapter(
        ProviderRuntimeConfig(
            provider_id="provider_openai",
            provider_family="openai",
            model="gpt-5.2",
            secret_ref_name="",
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
        ),
        transport=transport,
    )
    request = ProviderRuntimeRequest(
        messages=[ProviderMessage(role="user", content="hi")],
        metadata={
            "operator_policy": {
                "policy_id": "policy_provider_runtime",
                "required_operator": True,
                "allowed_operator_groups": ["prod-deploy"],
                "allowed_operator_subjects": [],
                "required_operator_issuer": None,
            }
        },
    )

    with pytest.raises(ProviderRuntimeError, match="operator groups denied by policy"):
        adapter.execute(request)

    assert transport.calls == 0


def test_provider_request_enforces_credential_policy_before_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    monkeypatch.setenv("CRAIK_HOME", str(paths.home))
    AuthProfileStore(paths.home).put(
        AuthProfile(
            id="openai:work",
            kind=CredentialKind.API_KEY,
            provider_family="openai",
            metadata={"env_var": "OPENAI_WORK_KEY"},
            created_at=datetime(2026, 5, 17, tzinfo=UTC),
        )
    )
    transport = _CountingTransport()
    adapter = OpenAIProviderAdapter(
        ProviderRuntimeConfig(
            provider_id="provider_openai",
            provider_family="openai",
            model="gpt-5.2",
            secret_ref_name="",
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
            auth_profile_id="openai:work",
        ),
        transport=transport,
    )
    request = ProviderRuntimeRequest(
        messages=[ProviderMessage(role="user", content="hi")],
        metadata={
            "credential_policy": {
                "policy_id": "policy_provider_runtime",
                "allowed_credential_kinds": ["secret-ref"],
                "allowed_credential_profiles": [],
            }
        },
    )

    with pytest.raises(ProviderRuntimeError, match="credential kind denied by policy"):
        adapter.execute(request)

    assert transport.calls == 0


def test_provider_request_denies_unauthorized_operator_for_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    monkeypatch.setenv("CRAIK_HOME", str(paths.home))
    OperatorSessionStore(paths.home).put(
        OperatorSession(
            subject="operator-123",
            email="operator@example.test",
            display_name="Operator",
            groups=["platform"],
            issuer="https://issuer.example.test",
            id_token_jti="token-1",
            expires_at=datetime(2026, 5, 18, tzinfo=UTC),
        )
    )
    AuthProfileStore(paths.home).put(
        AuthProfile(
            id="openai:work",
            kind=CredentialKind.API_KEY,
            provider_family="openai",
            metadata={"env_var": "OPENAI_WORK_KEY"},
            created_at=datetime(2026, 5, 17, tzinfo=UTC),
            authorized_operator_groups=["prod-deploy"],
        )
    )
    transport = _CountingTransport()
    adapter = OpenAIProviderAdapter(
        ProviderRuntimeConfig(
            provider_id="provider_openai",
            provider_family="openai",
            model="gpt-5.2",
            secret_ref_name="",
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
            auth_profile_id="openai:work",
        ),
        transport=transport,
    )

    with pytest.raises(ProviderRuntimeError, match="not authorized"):
        adapter.execute(
            ProviderRuntimeRequest(messages=[ProviderMessage(role="user", content="hi")])
        )

    assert transport.calls == 0


def test_provider_request_allows_authorized_operator_for_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    monkeypatch.setenv("CRAIK_HOME", str(paths.home))
    OperatorSessionStore(paths.home).put(
        OperatorSession(
            subject="operator-123",
            email="operator@example.test",
            display_name="Operator",
            groups=["platform"],
            issuer="https://issuer.example.test",
            id_token_jti="token-1",
            expires_at=datetime(2026, 5, 18, tzinfo=UTC),
        )
    )
    AuthProfileStore(paths.home).put(
        AuthProfile(
            id="openai:work",
            kind=CredentialKind.API_KEY,
            provider_family="openai",
            metadata={"env_var": "OPENAI_WORK_KEY"},
            created_at=datetime(2026, 5, 17, tzinfo=UTC),
            authorized_operators=["operator-123"],
        )
    )
    adapter = OpenAIProviderAdapter(
        ProviderRuntimeConfig(
            provider_id="provider_openai",
            provider_family="openai",
            model="gpt-5.2",
            secret_ref_name="",
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
            auth_profile_id="openai:work",
        )
    )

    result = adapter.execute(
        ProviderRuntimeRequest(messages=[ProviderMessage(role="user", content="hi")])
    )

    assert result.text


def test_provider_backed_runner_records_credential_policy_denial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    monkeypatch.setenv("CRAIK_HOME", str(paths.home))
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        AuthProfileStore(paths.home).put(
            AuthProfile(
                id="openai:work",
                kind=CredentialKind.API_KEY,
                provider_family="openai",
                metadata={"env_var": "OPENAI_WORK_KEY"},
                created_at=datetime(2026, 5, 17, tzinfo=UTC),
            )
        )
        policy = PolicyEnvelope(
            id="policy_provider_runtime",
            task_id="task_provider_runtime",
            actor="runner:provider_openai",
            profile="strict",
            allowed_credential_kinds=["secret-ref"],
        )
        store.put_policy_envelope(policy)
        runner = ProviderBackedStepRunner(
            store=store,
            adapter=OpenAIProviderAdapter(
                ProviderRuntimeConfig(
                    provider_id="provider_openai",
                    provider_family="openai",
                    model="gpt-5.2",
                    secret_ref_name="",
                    docs_refs=list(OPENAI_OFFICIAL_DOCS),
                    auth_profile_id="openai:work",
                )
            ),
            compiled_prompt=CompiledPrompt(
                id="compiled_provider_runtime",
                task_id="task_provider_runtime",
                case_file_id="case_provider_runtime",
                policy_envelope_id="policy_provider_runtime",
                runner_id="provider_openai",
                runner_mode="fixture",
                prompt="Run the provider-backed step.",
            ),
            actor="runner:provider_openai",
        )

        result = runner.run_step(
            RunnerStepRequest(
                id="runner_step_request_provider_runtime",
                run_id="run_provider_runtime",
                task_id="task_provider_runtime",
                phase="act",
                runner=RunnerMetadata(
                    id="provider_openai",
                    name="OpenAI Provider",
                    adapter="provider",
                    adapter_version="0.1.0",
                    mode="fixture",
                ),
                policy_envelope_id="policy_provider_runtime",
                expected_output_schemas=["craik.runner_step_result"],
                input_prompt="Act.",
                created_at=datetime(2026, 5, 17, tzinfo=UTC),
            )
        )
        receipt = store.get_receipt(result.receipt_ids[0])
    finally:
        store.close()

    assert result.status == "blocked"
    assert result.summary == "credential kind denied by policy"
    assert receipt is not None
    assert receipt.capability == "credential.use"
    assert receipt.result.status == "denied"


def test_provider_receipt_names_matched_operator_policy_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    monkeypatch.setenv("CRAIK_HOME", str(paths.home))
    OperatorSessionStore(paths.home).put(
        OperatorSession(
            subject="operator-123",
            email="operator@example.test",
            display_name="Operator",
            groups=["platform", "prod-deploy"],
            issuer="https://issuer.example.test",
            id_token_jti="token-1",
            expires_at=datetime(2026, 5, 18, tzinfo=UTC),
        )
    )
    adapter = _openai_adapter()
    request = ProviderRuntimeRequest(
        messages=[ProviderMessage(role="user", content="hi")],
        metadata={
            "operator_policy": {
                "policy_id": "policy_provider_runtime",
                "required_operator": True,
                "allowed_operator_groups": ["prod-deploy"],
                "allowed_operator_subjects": [],
                "required_operator_issuer": "https://issuer.example.test",
            }
        },
    )
    result = adapter.execute(request)
    receipt = provider_runtime_receipt(
        adapter=adapter,
        request=request,
        result=result,
        task_id="task_provider_runtime",
        policy_envelope_id="policy_provider_runtime",
        receipt_id="receipt_provider_runtime",
        actor="agent:codex",
    )

    assert request.metadata["operator_policy_matched_group"] == "prod-deploy"
    assert receipt.result.metadata["operator_policy_matched_group"] == "prod-deploy"
    assert receipt.operator_groups == ["platform", "prod-deploy"]


def test_live_provider_requires_first_use_credential_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRAIK_HOME", str(tmp_path))
    AuthProfileStore(tmp_path).put(
        AuthProfile(
            id="openai:work",
            kind=CredentialKind.API_KEY,
            provider_family="openai",
            metadata={"env_var": "OPENAI_WORK_KEY"},
            created_at=datetime(2026, 5, 17, tzinfo=UTC),
        )
    )
    transport = _CountingTransport()
    adapter = OpenAIProviderAdapter(
        ProviderRuntimeConfig(
            provider_id="provider_openai",
            provider_family="openai",
            model="gpt-5.2",
            secret_ref_name="",
            live_enabled=True,
            auth_profile_id="openai:work",
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
        ),
        transport=transport,
    )
    request = ProviderRuntimeRequest(
        messages=[ProviderMessage(role="user", content="hi")],
        metadata={"run_id": "run_approval"},
    )

    with pytest.raises(CredentialApprovalRequiredError, match="craik auth approve"):
        adapter.execute(request)

    assert transport.calls == 0


def test_live_provider_approved_first_use_marks_profile_used(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRAIK_HOME", str(tmp_path))
    store = AuthProfileStore(tmp_path)
    store.put(
        AuthProfile(
            id="openai:work",
            kind=CredentialKind.API_KEY,
            provider_family="openai",
            metadata={"env_var": "OPENAI_WORK_KEY"},
            created_at=datetime(2026, 5, 17, tzinfo=UTC),
        )
    )
    store.approve("openai:work", run_id="run_approval", approved_by="operator:local")
    transport = _CountingTransport()
    adapter = OpenAIProviderAdapter(
        ProviderRuntimeConfig(
            provider_id="provider_openai",
            provider_family="openai",
            model="gpt-5.2",
            secret_ref_name="",
            live_enabled=True,
            auth_profile_id="openai:work",
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
        ),
        transport=transport,
    )

    adapter.execute(
        ProviderRuntimeRequest(
            messages=[ProviderMessage(role="user", content="hi")],
            metadata={"run_id": "run_approval"},
        )
    )

    profile = store.get("openai:work")
    assert transport.calls == 1
    assert profile.last_status == "ok"
    assert profile.last_used_at is not None


class _CountingTransport:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def family(self) -> ProviderFamily:
        return "openai"

    def send(self, payload: dict[str, Any], *, stream: bool) -> Iterator[dict[str, Any]]:
        self.calls += 1
        yield {
            "id": "resp_counting",
            "model": "gpt-5.2",
            "output_text": "ok",
        }
