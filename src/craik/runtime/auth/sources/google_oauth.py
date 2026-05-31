"""Gemini and Vertex OAuth support via Google Application Default Credentials."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.auth import default as google_auth_default
from google.auth.exceptions import DefaultCredentialsError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

from craik.runtime.auth.profile import AuthProfile, CredentialKind, CredentialStatus

GEMINI_OAUTH_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
GEMINI_OAUTH_BILLING_SURFACE = "gcp-project"
GEMINI_ADC_CREDENTIAL_SOURCE = "adc"
GEMINI_SERVICE_ACCOUNT_CREDENTIAL_SOURCE = "service_account"

GoogleCredentials = Any
DefaultCredentialsResolver = Callable[[list[str]], tuple[GoogleCredentials, str | None]]
ServiceAccountLoader = Callable[[str, list[str]], GoogleCredentials]
RefreshRequestFactory = Callable[[], GoogleAuthRequest]


class GoogleOAuthError(RuntimeError):
    """Raised when Gemini credential resolution fails."""


@dataclass(frozen=True)
class GeminiCredentialResult:
    """Resolved Gemini credentials and the AuthProfile that records their source."""

    profile: AuthProfile
    gcp_project_id: str
    credentials: GoogleCredentials

    def status(self) -> CredentialStatus:
        """Return an OAuth-specific credential status without token material."""
        return CredentialStatus(status="ok")


def resolve_via_adc(
    *,
    scopes: list[str] | None = None,
    profile_id: str = "google:vertex",
    resolver: DefaultCredentialsResolver = google_auth_default,
) -> GeminiCredentialResult:
    """Resolve Gemini credentials from Google Application Default Credentials."""
    resolved_scopes = scopes or GEMINI_OAUTH_SCOPES
    try:
        credentials, project_id = resolver(resolved_scopes)
    except DefaultCredentialsError as exc:
        raise GoogleOAuthError(
            "No Google Cloud credentials found for Gemini. Run `gcloud auth "
            "application-default login` or use `craik auth login gemini "
            "--service-account <path>`."
        ) from exc
    except OSError as exc:
        raise GoogleOAuthError("Gemini ADC credential resolution failed") from exc
    if not project_id:
        raise GoogleOAuthError(
            "Gemini ADC credentials did not include a GCP project id. Set an active "
            "gcloud project or use `craik auth login gemini --service-account <path>`."
        )
    return GeminiCredentialResult(
        profile=_google_profile(
            profile_id=profile_id,
            credential_source=GEMINI_ADC_CREDENTIAL_SOURCE,
            project_id=project_id,
            scopes=resolved_scopes,
        ),
        gcp_project_id=project_id,
        credentials=credentials,
    )


def resolve_via_service_account(
    *,
    json_path: Path,
    scopes: list[str] | None = None,
    profile_id: str = "google:vertex",
    loader: ServiceAccountLoader | None = None,
) -> GeminiCredentialResult:
    """Resolve Gemini credentials from a service-account JSON file."""
    resolved_scopes = scopes or GEMINI_OAUTH_SCOPES
    resolved_path = json_path.expanduser()
    if not resolved_path.is_file():
        raise GoogleOAuthError(f"Gemini service-account file not found: {resolved_path}")
    try:
        if loader is None:
            credentials = service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
                str(resolved_path),
                scopes=resolved_scopes,
            )
        else:
            credentials = loader(str(resolved_path), resolved_scopes)
    except (OSError, ValueError) as exc:
        raise GoogleOAuthError("Gemini service-account credential resolution failed") from exc
    project_id = getattr(credentials, "project_id", None)
    if not isinstance(project_id, str) or not project_id:
        raise GoogleOAuthError("Gemini service-account credentials did not include a project id")
    return GeminiCredentialResult(
        profile=_google_profile(
            profile_id=profile_id,
            credential_source=GEMINI_SERVICE_ACCOUNT_CREDENTIAL_SOURCE,
            project_id=project_id,
            scopes=resolved_scopes,
            service_account_path=resolved_path,
        ),
        gcp_project_id=project_id,
        credentials=credentials,
    )


def headers_for_credentials(
    credentials: GoogleCredentials,
    *,
    refresh_request_factory: RefreshRequestFactory = GoogleAuthRequest,
) -> dict[str, str]:
    """Return a Gemini Bearer header, refreshing Google credentials when needed."""
    token = getattr(credentials, "token", None)
    expired = bool(getattr(credentials, "expired", False))
    if expired or not token:
        try:
            credentials.refresh(refresh_request_factory())
        except Exception as exc:  # noqa: BLE001
            raise GoogleOAuthError("Gemini credentials could not be refreshed") from exc
        token = getattr(credentials, "token", None)
    if not isinstance(token, str) or not token:
        raise GoogleOAuthError("Gemini credentials did not produce an access token")
    return {"Authorization": f"Bearer {token}"}


def headers_for_profile(profile: AuthProfile) -> dict[str, str]:
    """Resolve and return Gemini authorization headers for an ADC/service-account profile."""
    source = profile.metadata.get("credential_source")
    if source == GEMINI_ADC_CREDENTIAL_SOURCE:
        result = resolve_via_adc(
            scopes=profile.oauth_scope_list or GEMINI_OAUTH_SCOPES,
            profile_id=profile.id,
        )
        return headers_for_credentials(result.credentials)
    if source == GEMINI_SERVICE_ACCOUNT_CREDENTIAL_SOURCE:
        path = profile.metadata.get("service_account_path")
        if not isinstance(path, str) or not path:
            raise GoogleOAuthError(
                "Gemini service-account OAuth profile is missing service_account_path"
            )
        result = resolve_via_service_account(
            json_path=Path(path),
            scopes=profile.oauth_scope_list or GEMINI_OAUTH_SCOPES,
            profile_id=profile.id,
        )
        return headers_for_credentials(result.credentials)
    raise GoogleOAuthError("Gemini OAuth profile requires credential_source adc or service_account")


def store_google_adc_profile(
    *,
    profile_id: str = "google:vertex",
    project_id: str | None = None,
    resolver: DefaultCredentialsResolver = google_auth_default,
    env: dict[str, str] | None = None,
) -> GeminiCredentialResult:
    """Resolve ADC credentials, store their profile, and return the resolved credentials."""
    from craik.runtime.auth.guided_setup import default_pool_for_profile
    from craik.runtime.auth.pool import CredentialPool
    from craik.runtime.auth.store import AuthProfileStore

    result = resolve_via_adc(profile_id=profile_id, resolver=resolver)
    if project_id and project_id != result.gcp_project_id:
        result = GeminiCredentialResult(
            profile=result.profile.model_copy(
                update={
                    "metadata": result.profile.metadata
                    | {"gcp_project_id": project_id, "operator_project_id": project_id}
                }
            ),
            gcp_project_id=project_id,
            credentials=result.credentials,
        )
    AuthProfileStore.from_env(env).put(result.profile)
    CredentialPool.from_env(env).put(default_pool_for_profile(result.profile))
    return result


def store_google_service_account_profile(
    *,
    json_path: Path,
    profile_id: str = "google:vertex",
    env: dict[str, str] | None = None,
) -> GeminiCredentialResult:
    """Resolve service-account credentials, store their profile, and return them."""
    from craik.runtime.auth.guided_setup import default_pool_for_profile
    from craik.runtime.auth.pool import CredentialPool
    from craik.runtime.auth.store import AuthProfileStore

    result = resolve_via_service_account(json_path=json_path, profile_id=profile_id)
    AuthProfileStore.from_env(env).put(result.profile)
    CredentialPool.from_env(env).put(default_pool_for_profile(result.profile))
    return result


def _google_profile(
    *,
    profile_id: str,
    credential_source: str,
    project_id: str,
    scopes: list[str],
    service_account_path: Path | None = None,
) -> AuthProfile:
    metadata = {
        "source": "provider-oauth",
        "provider": "google",
        "billing_surface": GEMINI_OAUTH_BILLING_SURFACE,
        "credential_source": credential_source,
        "gcp_project_id": project_id,
    }
    if service_account_path is not None:
        metadata["service_account_path"] = str(service_account_path)
    return AuthProfile(
        id=profile_id,
        kind=CredentialKind.OAUTH,
        provider_family="google",
        metadata=metadata,
        created_at=datetime.now(UTC),
        last_status="ok",
        oauth_scope_list=scopes,
    )


# Deprecated alias; use GoogleOAuthError (gemini→google rename).
GeminiOAuthError = GoogleOAuthError
# Deprecated alias; use store_google_adc_profile (gemini→google rename).
store_gemini_adc_profile = store_google_adc_profile
# Deprecated alias; use store_google_service_account_profile (gemini→google rename).
store_gemini_service_account_profile = store_google_service_account_profile


__all__ = [
    "GEMINI_ADC_CREDENTIAL_SOURCE",
    "GEMINI_OAUTH_BILLING_SURFACE",
    "GEMINI_OAUTH_SCOPES",
    "GEMINI_SERVICE_ACCOUNT_CREDENTIAL_SOURCE",
    "GeminiCredentialResult",
    "GeminiOAuthError",
    "GoogleOAuthError",
    "headers_for_credentials",
    "headers_for_profile",
    "resolve_via_adc",
    "resolve_via_service_account",
    "store_gemini_adc_profile",
    "store_gemini_service_account_profile",
    "store_google_adc_profile",
    "store_google_service_account_profile",
]
