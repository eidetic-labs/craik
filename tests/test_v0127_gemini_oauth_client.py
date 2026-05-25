from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from google.auth.exceptions import DefaultCredentialsError

from craik.runtime.auth.profile import CredentialKind
from craik.runtime.auth.sources.gemini_oauth import (
    GEMINI_ADC_CREDENTIAL_SOURCE,
    GEMINI_OAUTH_BILLING_SURFACE,
    GEMINI_OAUTH_SCOPES,
    GEMINI_SERVICE_ACCOUNT_CREDENTIAL_SOURCE,
    GeminiOAuthError,
    headers_for_credentials,
    resolve_via_adc,
    resolve_via_service_account,
)


class _FakeCredentials:
    def __init__(
        self,
        *,
        token: str | None = "access-token",
        expired: bool = False,
        project_id: str = "craik-project",
    ) -> None:
        self.token = token
        self.expired = expired
        self.project_id = project_id
        self.refresh_count = 0

    def refresh(self, request: object) -> None:
        self.refresh_count += 1
        self.token = "fresh-access-token"
        self.expired = False


def test_resolve_via_adc_returns_oauth_profile_without_keyring_handles() -> None:
    credentials = _FakeCredentials()

    def _resolver(scopes: list[str]):
        assert scopes == GEMINI_OAUTH_SCOPES
        return credentials, "craik-project"

    result = resolve_via_adc(resolver=_resolver)

    assert result.credentials is credentials
    assert result.gcp_project_id == "craik-project"
    assert result.profile.kind is CredentialKind.OAUTH
    assert result.profile.provider_family == "gemini"
    assert result.profile.metadata["credential_source"] == GEMINI_ADC_CREDENTIAL_SOURCE
    assert result.profile.metadata["gcp_project_id"] == "craik-project"
    assert result.profile.metadata["billing_surface"] == GEMINI_OAUTH_BILLING_SURFACE
    assert result.profile.oauth_token_keyring_handle is None
    assert result.profile.oauth_refresh_keyring_handle is None


def test_resolve_via_adc_reports_gcloud_remediation() -> None:
    def _resolver(scopes: list[str]):
        raise DefaultCredentialsError("missing adc")

    with pytest.raises(GeminiOAuthError, match="gcloud auth application-default login"):
        resolve_via_adc(resolver=_resolver)


def test_resolve_via_service_account_returns_project_profile(tmp_path: Path) -> None:
    key_path = tmp_path / "service-account.json"
    key_path.write_text("{}", encoding="utf-8")
    credentials = _FakeCredentials(project_id="service-project")

    def _loader(path: str, scopes: list[str]):
        assert path == str(key_path)
        assert scopes == GEMINI_OAUTH_SCOPES
        return credentials

    result = resolve_via_service_account(json_path=key_path, loader=_loader)

    assert result.credentials is credentials
    assert result.gcp_project_id == "service-project"
    assert result.profile.metadata["credential_source"] == GEMINI_SERVICE_ACCOUNT_CREDENTIAL_SOURCE
    assert result.profile.metadata["service_account_path"] == str(key_path)


def test_headers_for_credentials_refreshes_expired_credentials() -> None:
    credentials = _FakeCredentials(token=None, expired=True)

    headers = headers_for_credentials(credentials, refresh_request_factory=lambda: object())

    assert headers == {"Authorization": "Bearer fresh-access-token"}
    assert credentials.refresh_count == 1


def test_headers_for_credentials_rejects_missing_token_after_refresh() -> None:
    class _BrokenCredentials(_FakeCredentials):
        def refresh(self, request: object) -> None:
            self.refresh_count += 1
            self.token = None

    with pytest.raises(GeminiOAuthError, match="access token"):
        headers_for_credentials(
            _BrokenCredentials(token=None, expired=True),
            refresh_request_factory=lambda: object(),
        )


def test_gemini_adc_profile_accepts_metadata_schema() -> None:
    result = resolve_via_adc(resolver=lambda scopes: (_FakeCredentials(), "craik-project"))

    restored = result.profile.model_copy(update={"created_at": datetime(2026, 5, 25, tzinfo=UTC)})

    assert restored.metadata["credential_source"] == "adc"
