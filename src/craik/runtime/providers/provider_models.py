"""Provider runtime request, result, and protocol models."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Protocol

from pydantic import Field

from craik.contracts.models import CraikModel
from craik.runtime.providers.provider_config import ProviderRuntimeConfig
from craik.runtime.providers.provider_transport import ProviderFamily, ProviderTransport

ProviderMessageRole = Literal["system", "user", "assistant", "tool"]


class ProviderRuntimeError(RuntimeError):
    """Base error for provider runtime failures."""


class ProviderLiveAccessNotConfiguredError(ProviderRuntimeError):
    """Raised when live provider access is attempted without explicit configuration."""


class CredentialApprovalRequiredError(ProviderRuntimeError):
    """Raised when a live provider credential requires first-use approval."""


class ProviderMessage(CraikModel):
    """Provider-neutral chat message."""

    role: ProviderMessageRole
    content: str


class ProviderTool(CraikModel):
    """Provider-neutral tool definition."""

    name: str
    description: str
    input_schema: dict[str, Any]


class ProviderRuntimeRequest(CraikModel):
    """Provider-neutral request used by runtime adapters."""

    messages: list[ProviderMessage] = Field(min_length=1)
    tools: list[ProviderTool] = Field(default_factory=list)
    structured_output_schema: dict[str, Any] | None = None
    structured_output_name: str = "craik_structured_output"
    max_output_tokens: int = Field(default=1024, ge=1)
    temperature: float | None = Field(default=None, ge=0)
    service_tier: str | None = None
    reasoning_effort: str | None = None
    provider_options: dict[str, Any] = Field(default_factory=dict)
    stream: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderRuntimeResult(CraikModel):
    """Provider-neutral response summary."""

    provider_id: str
    provider_family: ProviderFamily
    model: str
    text: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    structured_output: dict[str, Any] | None = None
    structured_output_name: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    response_id: str | None = None
    redacted: bool = True


class ProviderRuntimeChunk(CraikModel):
    """Provider-neutral streaming response chunk."""

    provider_id: str
    provider_family: ProviderFamily
    model: str
    text_delta: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)
    response_id: str | None = None
    finish_reason: str | None = None
    redacted: bool = True


class ProviderRuntimeErrorDecision(CraikModel):
    """Provider-neutral retry decision for an API error."""

    provider_family: ProviderFamily
    status_code: int | None
    error_type: str | None
    retryable: bool
    retry_after_seconds: int | None = None
    reason: str


class ProviderRuntimeAdapter(Protocol):
    """Runtime adapter contract for provider-specific payloads."""

    config: ProviderRuntimeConfig
    transport: ProviderTransport

    def execute(
        self,
        request: ProviderRuntimeRequest,
        *,
        stream_callback: Callable[[str], None] | None = None,
    ) -> ProviderRuntimeResult:
        """Execute one provider request through the configured transport."""
        raise NotImplementedError

    def build_payload(self, request: ProviderRuntimeRequest) -> dict[str, Any]:
        """Build a provider-specific request payload."""
        raise NotImplementedError

    def normalize_response(self, response: dict[str, Any]) -> ProviderRuntimeResult:
        """Normalize a provider response payload."""
        raise NotImplementedError

    def classify_error(
        self,
        *,
        status_code: int | None,
        error_type: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> ProviderRuntimeErrorDecision:
        """Classify whether an error is retryable."""
        raise NotImplementedError

    def require_live_access(self) -> None:
        """Raise unless live API access was explicitly enabled."""
        raise NotImplementedError
