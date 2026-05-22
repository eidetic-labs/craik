"""Credential profile contracts for pluggable provider authentication."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import Field, field_validator, model_validator

from craik.contracts.models import CapabilityReceipt, CraikModel
from craik.runtime.providers.provider_transport import ProviderFamily

CredentialHealthStatus = Literal["unknown", "ok", "expired", "rejected", "rate_limited"]


class CredentialKind(StrEnum):
    """Supported credential acquisition modes."""

    API_KEY = "api-key"
    OAUTH_TOKEN = "oauth-token"
    SECRET_REF = "secret-ref"
    STIGMEM_REF = "stigmem-ref"
    CLI_BRIDGE = "cli-bridge"
    MARKER = "marker"


class CredentialStatus(CraikModel):
    """Cheap health verdict for a credential source."""

    status: CredentialHealthStatus = "unknown"
    detail: str | None = None
    expires_at: datetime | None = None


class AuthProfile(CraikModel):
    """Named provider credential profile stored in agent auth state."""

    id: str
    kind: CredentialKind
    provider_family: ProviderFamily
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    last_used_at: datetime | None = None
    last_status: CredentialHealthStatus = "unknown"
    authorized_operators: list[str] | None = None
    authorized_operator_groups: list[str] | None = None
    authorization_provenance: list[CapabilityReceipt] = Field(default_factory=list)
    redaction_patterns: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_profile_id(self) -> AuthProfile:
        """Require profile IDs to be namespaced by provider family."""
        if ":" not in self.id:
            raise ValueError("auth profile id must use <provider_family>:<name>")
        family, name = self.id.split(":", 1)
        if family != self.provider_family:
            raise ValueError("auth profile id provider family must match provider_family")
        if not name.strip():
            raise ValueError("auth profile id requires a non-empty profile name")
        if self.id.strip() != self.id or any(char.isspace() for char in self.id):
            raise ValueError("auth profile id must not contain whitespace")
        return self

    @field_validator("redaction_patterns")
    @classmethod
    def validate_redaction_patterns(cls, patterns: list[str]) -> list[str]:
        """Require profile-scoped redaction patterns to be valid regexes."""
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError("auth profile redaction pattern is invalid") from exc
        return patterns

    @field_validator("authorized_operators", "authorized_operator_groups")
    @classmethod
    def validate_authorization_scope(
        cls,
        values: list[str] | None,
    ) -> list[str] | None:
        """Reject empty allowlists; use None for legacy unscoped visibility."""
        if values == []:
            raise ValueError("authorization scope must be None or a non-empty list")
        return values


class CredentialSource(Protocol):
    """Provider credential source that can produce request headers."""

    def headers_for(self, family: ProviderFamily) -> dict[str, str]:
        """Return provider-specific authorization headers."""
        raise NotImplementedError

    def status(self) -> CredentialStatus:
        """Return a cheap health verdict without exposing credential material."""
        raise NotImplementedError
