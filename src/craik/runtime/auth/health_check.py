"""Provider credential health checks for capture-and-cache auth."""

from __future__ import annotations

import os
from typing import Any, Literal
from urllib import error as url_error
from urllib import request
from urllib.parse import urlsplit, urlunsplit

from craik.runtime.auth.profile import AuthProfile, CredentialStatus

HealthCheckStatus = Literal["ok", "rejected", "unknown"]
_DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS = 5.0
_HEALTH_CHECK_TIMEOUT_ENV = "CRAIK_AUTH_HEALTH_CHECK_TIMEOUT_S"
_ALLOWED_AUTH_HEALTH_URL_SCHEMES = frozenset({"http", "https"})


def health_check_profile_secret(
    profile: AuthProfile,
    secret: str,
    *,
    env: dict[str, str] | None = None,
) -> CredentialStatus:
    """Verify captured credential material without returning secret detail."""
    if not secret.strip():
        return _rejected(profile)
    if any(char.isspace() for char in secret):
        return _rejected(profile)
    try:
        health_request = _health_check_request(profile, secret)
        with _health_check_urlopen(
            health_request,
            timeout=_health_check_timeout(env),
        ) as response:
            status_code = response.getcode()
    except url_error.HTTPError as exc:
        status_code = exc.code
    except ValueError as exc:
        return CredentialStatus(
            status="unknown",
            detail=_health_check_unknown_detail(profile, str(exc)),
        )
    except (OSError, TimeoutError):
        return CredentialStatus(
            status="unknown",
            detail=_health_check_unknown_detail(profile, "network error"),
        )
    if status_code == 200:
        return CredentialStatus(status="ok")
    if status_code in {401, 403}:
        return _rejected(profile)
    return CredentialStatus(status="unknown", detail=_health_check_unknown_detail(profile, None))


def _health_check_request(profile: AuthProfile, secret: str) -> request.Request:
    provider = str(profile.metadata.get("provider") or profile.provider_family)
    url = _health_check_url(profile, provider)
    return request.Request(
        url,
        headers=_health_check_headers(provider, secret),
        method="GET",
    )


def _health_check_headers(provider: str, secret: str) -> dict[str, str]:
    if provider == "anthropic":
        return {
            "x-api-key": secret,
            "anthropic-version": "2023-06-01",
        }
    if provider == "gemini":
        return {"x-goog-api-key": secret}
    return {"Authorization": f"Bearer {secret}"}


def _health_check_url(profile: AuthProfile, provider: str) -> str:
    base_url = profile.metadata.get("base_url")
    if not isinstance(base_url, str) or not base_url.strip():
        base_url = _default_health_check_base_url(provider)
    split = urlsplit(base_url)
    if split.scheme and split.scheme.lower() not in _ALLOWED_AUTH_HEALTH_URL_SCHEMES:
        raise ValueError("provider health-check base_url must use http or https")
    if not split.scheme or not split.netloc:
        raise ValueError("provider health-check base_url must be an absolute URL")
    path = split.path.rstrip("/")
    suffix = "/v1beta/models" if provider == "gemini" else "/v1/models"
    if path.endswith("/v1") or path.endswith("/v1beta"):
        path = f"{path}/models"
    elif not path.endswith("/models"):
        path = f"{path}{suffix}"
    return urlunsplit((split.scheme, split.netloc, path, "", ""))


def _default_health_check_base_url(provider: str) -> str:
    if provider == "anthropic":
        return "https://api.anthropic.com"
    if provider == "gemini":
        return "https://generativelanguage.googleapis.com"
    return "https://api.openai.com"


def _health_check_timeout(env: dict[str, str] | None) -> float:
    values = os.environ if env is None else env
    raw = values.get(_HEALTH_CHECK_TIMEOUT_ENV)
    if raw is None:
        return _DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError:
        return _DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS
    return timeout if timeout > 0 else _DEFAULT_HEALTH_CHECK_TIMEOUT_SECONDS


def _health_check_urlopen(
    health_request: request.Request,
    *,
    timeout: float,
) -> Any:
    split = urlsplit(health_request.full_url)
    if split.scheme.lower() not in _ALLOWED_AUTH_HEALTH_URL_SCHEMES:
        raise ValueError("provider health-check URL must use http or https")
    return request.urlopen(health_request, timeout=timeout)  # nosec B310


def _health_check_unknown_detail(profile: AuthProfile, detail: str | None) -> str:
    provider = str(profile.metadata.get("provider") or profile.provider_family)
    message = (
        f"Could not verify {provider} credential with the provider health endpoint. "
        f"Re-run craik auth login {provider} after checking provider status."
    )
    if detail:
        return f"{message} {detail}"
    return message


def _rejected(profile: AuthProfile) -> CredentialStatus:
    provider = str(profile.metadata.get("provider") or profile.provider_family)
    family = provider.replace("_", " ").title()
    return CredentialStatus(
        status="rejected",
        detail=f"Your {family} key was rejected. Re-run craik auth login {provider}.",
    )


__all__ = ["HealthCheckStatus", "health_check_profile_secret"]
