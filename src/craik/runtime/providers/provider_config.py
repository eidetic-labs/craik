"""Provider runtime configuration and official documentation references."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from pydantic import Field, model_validator

from craik.contracts.models import CraikModel
from craik.runtime.providers.provider_transport import ProviderFamily
from craik.runtime.providers.provider_url_safety import (
    ProviderURLSafetyError,
    assert_safe_provider_url,
)
from craik.runtime.secrets import SecretRef, SecretResolver

OPENAI_OFFICIAL_DOCS = (
    "https://platform.openai.com/docs/api-reference/responses",
    "https://platform.openai.com/docs/guides/streaming-responses",
    "https://platform.openai.com/docs/guides/structured-outputs",
    "https://platform.openai.com/docs/guides/tools",
)
ANTHROPIC_OFFICIAL_DOCS = (
    "https://docs.anthropic.com/en/api/messages",
    "https://docs.anthropic.com/claude/reference/messages-streaming",
    "https://docs.anthropic.com/en/docs/build-with-claude/tool-use",
    "https://docs.anthropic.com/en/docs/about-claude/models/all-models",
    "https://docs.anthropic.com/en/api/rate-limits",
)
GEMINI_OFFICIAL_DOCS = (
    "https://ai.google.dev/api/generate-content",
    "https://ai.google.dev/gemini-api/docs/function-calling",
    "https://ai.google.dev/gemini-api/docs/structured-output",
    "https://ai.google.dev/gemini-api/docs/models",
)


class ProviderRuntimeConfig(CraikModel):
    """Runtime configuration for one provider adapter."""

    provider_id: str
    provider_family: ProviderFamily
    model: str
    secret_ref_name: str
    base_url: str | None = None
    allow_local_base_url: bool = False
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=3, ge=0)
    live_enabled: bool = False
    auth_profile_id: str | None = None
    credential_pool_id: str | None = None
    last_auth_profile_id: str | None = Field(default=None, exclude=True)
    docs_verified_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    docs_refs: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_runtime_config(self) -> ProviderRuntimeConfig:
        """Keep live access explicit and credentials reference-only."""
        if self.secret_ref_name and any(
            token in self.secret_ref_name.lower() for token in ("sk-", "token=", "key=")
        ):
            raise ValueError(
                "provider runtime secret_ref_name must not contain raw secret material"
            )
        if self.auth_profile_id and self.credential_pool_id:
            raise ValueError(
                "provider runtime auth_profile_id and credential_pool_id are mutually exclusive"
            )
        if self.base_url:
            try:
                assert_safe_provider_url(
                    self.base_url,
                    allow_local=self.allow_local_base_url,
                )
            except ProviderURLSafetyError as exc:
                raise ValueError(str(exc)) from exc
        expected_refs: Sequence[str]
        if self.provider_family == "anthropic":
            expected_refs = ANTHROPIC_OFFICIAL_DOCS
        elif self.provider_family == "gemini":
            expected_refs = GEMINI_OFFICIAL_DOCS
        else:
            expected_refs = OPENAI_OFFICIAL_DOCS
        missing = [ref for ref in expected_refs if ref not in self.docs_refs]
        if missing:
            raise ValueError(f"provider runtime docs_refs missing official refs: {missing}")
        return self

    def resolve_secret(self, resolver: SecretResolver) -> str:
        """Resolve the configured secret reference at request time."""
        if not self.secret_ref_name:
            return ""
        return resolver.resolve(SecretRef(env_var=self.secret_ref_name))
