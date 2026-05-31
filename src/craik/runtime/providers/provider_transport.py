"""Provider transport protocol and fixture transport."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from craik.contracts.models import RunnerResultStatus

ProviderFamily = Literal["openai", "anthropic", "google", "gemini", "chat_completions"]


def normalize_provider_family(family: str) -> str:
    """Map deprecated provider-family aliases to their canonical token.

    "gemini" is the legacy token for Google's provider family; it is still
    accepted as input but normalized to the canonical "google".
    """
    return "google" if family == "gemini" else family


class ProviderTransport(Protocol):
    """Provider wire transport that yields normalized response chunks."""

    @property
    def family(self) -> ProviderFamily:
        """Provider API family this transport speaks."""
        raise NotImplementedError

    def send(self, payload: dict[str, Any], *, stream: bool) -> Iterator[dict[str, Any]]:
        """Send one provider payload and yield one or more response chunks."""
        raise NotImplementedError


class ProviderTransportError(RuntimeError):
    """Raised when provider transport fails before adapter normalization."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: str | None = None,
        headers: dict[str, str] | None = None,
        retry_after_seconds: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}
        self.retry_after_seconds = retry_after_seconds
        self.retryable = retryable


@dataclass(frozen=True)
class FixtureTransport:
    """Deterministic provider transport for tests and non-live runs."""

    family: ProviderFamily
    model: str
    response_id: str = "provider_response_fixture"
    phase: str = "fixture"
    status: RunnerResultStatus = "completed"
    stream_chunks: tuple[str, ...] = ()

    def send(self, payload: dict[str, Any], *, stream: bool) -> Iterator[dict[str, Any]]:
        """Yield a deterministic provider-shaped fixture response."""
        context = payload.get("_fixture", {})
        context = context if isinstance(context, dict) else {}
        if stream and self.stream_chunks:
            yield from _fixture_stream_response(
                provider_family=self.family,
                model=self.model,
                response_id=str(context.get("response_id") or self.response_id),
                chunks=self.stream_chunks,
            )
            return
        yield _fixture_response(
            provider_family=self.family,
            model=self.model,
            response_id=str(context.get("response_id") or self.response_id),
            phase=str(context.get("phase") or self.phase),
            status=cast(RunnerResultStatus, context.get("status") or self.status),
        )


def _fixture_response(
    *,
    provider_family: ProviderFamily,
    model: str,
    response_id: str,
    phase: str,
    status: RunnerResultStatus,
) -> dict[str, Any]:
    family = normalize_provider_family(provider_family)
    text = f"{family} fixture completed {phase} with status {status}."
    structured = {
        "phase": phase,
        "status": status,
        "summary": text,
    }
    if family == "openai":
        return {
            "id": response_id,
            "model": model,
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": text}]},
                {
                    "type": "function_call",
                    "id": f"fc_{phase}",
                    "call_id": f"call_{phase}",
                    "name": "record_runner_step",
                    "arguments": "{}",
                },
            ],
            "usage": {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
        }
    if family == "chat_completions":
        return {
            "id": response_id,
            "model": model,
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": text,
                        "tool_calls": [
                            {
                                "id": f"call_{phase}",
                                "type": "function",
                                "function": {
                                    "name": "record_runner_step",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }
    if family == "google":
        return {
            "responseId": response_id,
            "modelVersion": model,
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {"text": text},
                            {
                                "functionCall": {
                                    "name": "craik_structured_output",
                                    "args": structured,
                                }
                            },
                        ],
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 21,
                "candidatesTokenCount": 10,
                "totalTokenCount": 31,
            },
        }
    return {
        "id": response_id,
        "model": model,
        "content": [
            {"type": "text", "text": text},
            {
                "type": "tool_use",
                "id": f"toolu_{phase}",
                "name": "craik_structured_output",
                "input": structured,
            },
        ],
        "usage": {"input_tokens": 22, "output_tokens": 11},
    }


def _fixture_stream_response(
    *,
    provider_family: ProviderFamily,
    model: str,
    response_id: str,
    chunks: tuple[str, ...],
) -> Iterator[dict[str, Any]]:
    if provider_family != "chat_completions":
        yield _fixture_response(
            provider_family=provider_family,
            model=model,
            response_id=response_id,
            phase="stream",
            status="completed",
        )
        return
    for index, chunk in enumerate(chunks):
        final = index == len(chunks) - 1
        yield {
            "id": response_id,
            "model": model,
            "choices": [
                {
                    "delta": {"content": chunk},
                    "finish_reason": "stop" if final else None,
                }
            ],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": len(chunks),
                "total_tokens": 20 + len(chunks),
            }
            if final
            else {},
        }
