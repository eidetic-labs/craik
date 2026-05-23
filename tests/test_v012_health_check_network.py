from __future__ import annotations

from datetime import UTC, datetime
from urllib import error as url_error
from urllib.request import Request

import pytest

from craik.runtime.auth import health_check as auth_health_check
from craik.runtime.auth.profile import AuthProfile, CredentialKind


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self._status_code = status_code

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def getcode(self) -> int:
        return self._status_code


def _profile(provider: str, *, base_url: str | None = None) -> AuthProfile:
    metadata: dict[str, str] = {"provider": provider}
    if base_url is not None:
        metadata["base_url"] = base_url
    family = "chat_completions" if provider == "local" else provider
    name = "local" if provider == "local" else "default"
    return AuthProfile(
        id=f"{family}:{name}",
        kind=CredentialKind.KEYRING_REF,
        provider_family=family,
        metadata=metadata,
        created_at=datetime.now(UTC),
    )


@pytest.mark.parametrize(
    ("provider", "expected_url", "expected_header"),
    [
        ("openai", "https://api.openai.com/v1/models", "authorization"),
        ("anthropic", "https://api.anthropic.com/v1/models", "x-api-key"),
        (
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta/models",
            "x-goog-api-key",
        ),
    ],
)
def test_health_check_uses_provider_model_endpoint(
    monkeypatch,
    provider: str,
    expected_url: str,
    expected_header: str,
) -> None:
    seen: dict[str, object] = {}

    def _urlopen(health_request: Request, *, timeout: float) -> _FakeResponse:
        seen["url"] = health_request.full_url
        seen["headers"] = health_request.headers
        seen["timeout"] = timeout
        return _FakeResponse(200)

    monkeypatch.setattr(auth_health_check, "_health_check_urlopen", _urlopen)

    status = auth_health_check.health_check_profile_secret(
        _profile(provider),
        "provider-secret",
        env={"CRAIK_AUTH_HEALTH_CHECK_TIMEOUT_S": "1.25"},
    )

    assert status.status == "ok"
    assert seen["url"] == expected_url
    assert expected_header in {key.lower() for key in seen["headers"]}
    assert seen["timeout"] == 1.25


def test_health_check_local_base_url_uses_openai_compatible_models_endpoint(monkeypatch) -> None:
    seen: dict[str, str] = {}

    def _urlopen(health_request: Request, *, timeout: float) -> _FakeResponse:
        seen["url"] = health_request.full_url
        return _FakeResponse(200)

    monkeypatch.setattr(auth_health_check, "_health_check_urlopen", _urlopen)

    status = auth_health_check.health_check_profile_secret(
        _profile("local", base_url="http://localhost:11434/v1"),
        "local-secret",
        env={},
    )

    assert status.status == "ok"
    assert seen["url"] == "http://localhost:11434/v1/models"


def test_health_check_rejects_non_http_base_url_without_network(monkeypatch) -> None:
    def _urlopen(health_request: Request, *, timeout: float) -> _FakeResponse:
        raise AssertionError("health check should reject before network open")

    monkeypatch.setattr(auth_health_check, "_health_check_urlopen", _urlopen)

    status = auth_health_check.health_check_profile_secret(
        _profile("openai", base_url="file:///tmp/key"),
        "provider-secret",
        env={},
    )

    assert status.status == "unknown"
    assert "http or https" in (status.detail or "")
    assert "provider-secret" not in (status.detail or "")


@pytest.mark.parametrize("status_code", [401, 403])
def test_health_check_rejects_unauthorized_without_leaking_secret(
    monkeypatch,
    status_code: int,
) -> None:
    def _urlopen(health_request: Request, *, timeout: float) -> _FakeResponse:
        raise url_error.HTTPError(
            health_request.full_url,
            status_code,
            "nope Authorization: Bearer provider-secret",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(auth_health_check, "_health_check_urlopen", _urlopen)

    status = auth_health_check.health_check_profile_secret(
        _profile("openai"),
        "provider-secret",
        env={},
    )

    assert status.status == "rejected"
    assert "provider-secret" not in (status.detail or "")
    assert status.detail == "Your Openai key was rejected. Re-run craik auth login openai."


@pytest.mark.parametrize("raised", [TimeoutError("provider-secret"), OSError("token=secret")])
def test_health_check_network_failures_are_unknown_and_redacted(monkeypatch, raised) -> None:
    def _urlopen(health_request: Request, *, timeout: float) -> _FakeResponse:
        raise raised

    monkeypatch.setattr(auth_health_check, "_health_check_urlopen", _urlopen)

    status = auth_health_check.health_check_profile_secret(
        _profile("openai"),
        "provider-secret",
        env={},
    )

    assert status.status == "unknown"
    assert "provider-secret" not in (status.detail or "")
    assert "token=secret" not in (status.detail or "")


def test_health_check_unexpected_status_is_unknown(monkeypatch) -> None:
    def _urlopen(health_request: Request, *, timeout: float) -> _FakeResponse:
        return _FakeResponse(500)

    monkeypatch.setattr(auth_health_check, "_health_check_urlopen", _urlopen)

    status = auth_health_check.health_check_profile_secret(
        _profile("gemini"),
        "provider-secret",
        env={},
    )

    assert status.status == "unknown"
    assert "provider-secret" not in (status.detail or "")
