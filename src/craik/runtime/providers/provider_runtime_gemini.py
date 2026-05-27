"""Gemini provider runtime adapter."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from craik.runtime.policy.redaction import redact
from craik.runtime.providers.provider_config import ProviderRuntimeConfig
from craik.runtime.providers.provider_execution import execute_provider_request
from craik.runtime.providers.provider_models import (
    ProviderLiveAccessNotConfiguredError,
    ProviderMessage,
    ProviderRuntimeErrorDecision,
    ProviderRuntimeRequest,
    ProviderRuntimeResult,
    ProviderTool,
)
from craik.runtime.providers.provider_runtime_support import (
    _fixture_context,
    _json_object_or_none,
    _retry_after,
)
from craik.runtime.providers.provider_transport import (
    FixtureTransport,
    ProviderTransport,
)


class GeminiProviderAdapter:
    """Gemini generateContent payload and response normalization."""

    def __init__(
        self,
        config: ProviderRuntimeConfig,
        transport: ProviderTransport | None = None,
    ) -> None:
        if config.provider_family != "gemini":
            raise ValueError("GeminiProviderAdapter requires provider_family='gemini'")
        self.config = config
        self.transport = transport or FixtureTransport(family="gemini", model=config.model)

    def build_payload(self, request: ProviderRuntimeRequest) -> dict[str, Any]:
        system_parts = [
            {"text": message.content}
            for message in request.messages
            if message.role == "system"
        ]
        chat_messages = [message for message in request.messages if message.role != "system"]
        method = "streamGenerateContent?alt=sse" if request.stream else "generateContent"
        payload: dict[str, Any] = {
            "_path": f"/v1beta/models/{self.config.model}:{method}",
            "_fixture": _fixture_context(request),
            "contents": [_gemini_content(message) for message in chat_messages],
        }
        generation_config: dict[str, Any] = {}
        if request.max_output_tokens:
            generation_config["maxOutputTokens"] = request.max_output_tokens
        if request.temperature is not None:
            generation_config["temperature"] = request.temperature
        if request.reasoning_effort:
            generation_config["thinkingConfig"] = {"reasoningEffort": request.reasoning_effort}
        generation_config.update(
            {
                key: value
                for key, value in request.provider_options.items()
                if key
                not in {
                    "contents",
                    "generationConfig",
                    "maxOutputTokens",
                    "responseMimeType",
                    "responseSchema",
                    "systemInstruction",
                    "temperature",
                    "thinkingConfig",
                    "toolConfig",
                    "tools",
                }
            }
        )
        if request.structured_output_schema is not None:
            generation_config.update(
                {
                    "responseMimeType": "application/json",
                    "responseSchema": request.structured_output_schema,
                }
            )
        if generation_config:
            payload["generationConfig"] = generation_config
        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}
        if request.tools:
            payload["tools"] = [
                {"functionDeclarations": [_gemini_tool(tool) for tool in request.tools]}
            ]
            payload["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
        return payload

    def execute(
        self,
        request: ProviderRuntimeRequest,
        *,
        stream_callback: Callable[[str], None] | None = None,
    ) -> ProviderRuntimeResult:
        """Execute one Gemini generateContent request through the configured transport."""
        return execute_provider_request(self, request, stream_callback=stream_callback)

    def normalize_response(self, response: dict[str, Any]) -> ProviderRuntimeResult:
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for candidate in _gemini_candidates(response):
            content = candidate.get("content", {})
            if not isinstance(content, dict):
                continue
            for part in content.get("parts", []):
                if not isinstance(part, dict):
                    continue
                if "text" in part:
                    text_parts.append(str(part.get("text") or ""))
                function_call = part.get("functionCall")
                if isinstance(function_call, dict):
                    tool_calls.append(
                        {
                            "name": function_call.get("name"),
                            "arguments": redact(function_call.get("args", {})).value,
                        }
                    )
        text = "".join(text_parts)
        return ProviderRuntimeResult(
            provider_id=self.config.provider_id,
            provider_family="gemini",
            model=str(response.get("modelVersion", self.config.model)),
            text=text,
            tool_calls=tool_calls,
            structured_output=_json_object_or_none(text),
            usage=_gemini_usage(response.get("usageMetadata", {})),
            response_id=str(response.get("responseId")) if response.get("responseId") else None,
        )

    def classify_error(
        self,
        *,
        status_code: int | None,
        error_type: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> ProviderRuntimeErrorDecision:
        retryable = status_code in {408, 409, 429, 500, 502, 503, 504}
        return ProviderRuntimeErrorDecision(
            provider_family="gemini",
            status_code=status_code,
            error_type=error_type,
            retryable=retryable,
            retry_after_seconds=_retry_after(headers),
            reason=(
                "retryable Gemini API condition"
                if retryable
                else "non-retryable Gemini API condition"
            ),
        )

    def require_live_access(self) -> None:
        if not self.config.live_enabled:
            raise ProviderLiveAccessNotConfiguredError(
                "Gemini live access requires live_enabled=true and an external secret resolver"
            )


def _gemini_content(message: ProviderMessage) -> dict[str, Any]:
    role = "model" if message.role == "assistant" else "user"
    return {"role": role, "parts": [{"text": message.content}]}


def _gemini_tool(tool: ProviderTool) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.input_schema,
    }


def _gemini_candidates(response: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = response.get("candidates", [])
    if isinstance(candidates, list):
        return [candidate for candidate in candidates if isinstance(candidate, dict)]
    return []


def _gemini_usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    input_tokens = int(value.get("promptTokenCount", 0) or 0)
    output_tokens = int(value.get("candidatesTokenCount", 0) or 0)
    total_tokens = int(value.get("totalTokenCount", input_tokens + output_tokens) or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


__all__ = ["GeminiProviderAdapter"]
