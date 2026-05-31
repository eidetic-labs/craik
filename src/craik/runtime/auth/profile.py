"""Credential profile contracts for pluggable provider authentication."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import Field, field_validator, model_validator

from craik.contracts.models import CapabilityReceipt, CraikModel
from craik.runtime.providers.provider_transport import (
    ProviderFamily,
    normalize_provider_family,
)

CredentialHealthStatus = Literal["unknown", "ok", "expired", "rejected", "rate_limited"]


class CredentialKind(StrEnum):
    """Supported credential acquisition modes."""

    API_KEY = "api-key"
    OAUTH = "oauth"
    SECRET_REF = "secret-ref"
    KEYRING_REF = "keyring-ref"
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
    oauth_authorization_endpoint: str | None = None
    oauth_token_endpoint: str | None = None
    oauth_client_id: str | None = None
    oauth_scope_list: list[str] | None = None
    oauth_token_keyring_handle: str | None = None
    oauth_refresh_keyring_handle: str | None = None
    oauth_last_refreshed_at: datetime | None = None

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

    @model_validator(mode="after")
    def validate_oauth_fields(self) -> AuthProfile:
        """Require complete OAuth metadata for provider OAuth profiles."""
        if self.kind is not CredentialKind.OAUTH:
            return self
        if normalize_provider_family(self.provider_family) == "google" and self.metadata.get(
            "credential_source"
        ) in {
            "adc",
            "service_account",
        }:
            if self.oauth_scope_list is None or not self.oauth_scope_list:
                raise ValueError("oauth auth profiles require: oauth_scope_list")
            if any(not scope.strip() for scope in self.oauth_scope_list):
                raise ValueError("oauth_scope_list entries must be non-empty")
            if not isinstance(self.metadata.get("gcp_project_id"), str):
                raise ValueError("google oauth auth profiles require metadata.gcp_project_id")
            if self.metadata.get("credential_source") == "service_account" and not isinstance(
                self.metadata.get("service_account_path"), str
            ):
                raise ValueError(
                    "google service-account oauth profiles require service_account_path"
                )
            return self

        required_strings = {
            "oauth_authorization_endpoint": self.oauth_authorization_endpoint,
            "oauth_token_endpoint": self.oauth_token_endpoint,
            "oauth_client_id": self.oauth_client_id,
            "oauth_token_keyring_handle": self.oauth_token_keyring_handle,
            "oauth_refresh_keyring_handle": self.oauth_refresh_keyring_handle,
        }
        missing = [
            field for field, value in required_strings.items() if not value or not value.strip()
        ]
        if self.oauth_scope_list is None or not self.oauth_scope_list:
            missing.append("oauth_scope_list")
        elif any(not scope.strip() for scope in self.oauth_scope_list):
            raise ValueError("oauth_scope_list entries must be non-empty")

        if missing:
            formatted = ", ".join(missing)
            raise ValueError(f"oauth auth profiles require: {formatted}")
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
