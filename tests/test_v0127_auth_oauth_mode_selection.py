from __future__ import annotations

import json
from datetime import UTC, datetime

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.auth.login import AuthCaptureResult
from craik.runtime.auth.oauth_provider_login import OAuthLoginResult
from craik.runtime.auth.profile import AuthProfile, CredentialKind, CredentialStatus
from craik.runtime.shell.credential_storage import CredentialStorageStatus

runner = CliRunner()


def test_anthropic_defaults_to_oauth_when_mode_is_omitted(monkeypatch, tmp_path) -> None:
    called: dict[str, str] = {}

    def _browser_login(provider: str, **kwargs):
        called["provider"] = provider
        return OAuthLoginResult(
            capture=_capture_result("anthropic", CredentialKind.KEYRING_REF),
            authorization_url="https://claude.ai/oauth/authorize",
            browser_opened=False,
        )

    monkeypatch.setattr("craik.cli_auth_login.browser_oauth_login", _browser_login)

    result = runner.invoke(
        app,
        ["auth", "login", "anthropic", "--json"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    assert called == {"provider": "anthropic"}
    assert json.loads(result.stdout)["authorization_url"] == "https://claude.ai/oauth/authorize"


def test_gemini_defaults_to_oauth_when_mode_is_omitted(monkeypatch, tmp_path) -> None:
    called: dict[str, bool] = {}

    def _gemini_login(**kwargs):
        called["gemini"] = True
        return OAuthLoginResult(
            capture=_capture_result("gemini", CredentialKind.KEYRING_REF),
            authorization_url="gcloud auth application-default login",
            browser_opened=False,
        )

    monkeypatch.setattr("craik.cli_auth_login.gemini_oauth_login", _gemini_login)

    result = runner.invoke(
        app,
        ["auth", "login", "gemini", "--json"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    assert called == {"gemini": True}
    assert json.loads(result.stdout)["authorization_url"] == "gcloud auth application-default login"


def test_openai_defaults_to_api_key_when_mode_is_omitted(monkeypatch, tmp_path) -> None:
    captured: dict[str, str] = {}

    def _capture_login(provider: str, **kwargs):
        captured["provider"] = provider
        captured["credential"] = kwargs["credential"]
        return _capture_result(provider, CredentialKind.KEYRING_REF)

    def _browser_login(provider: str, **kwargs):
        raise AssertionError("OpenAI defaults to api-key mode until OAuth registration exists")

    monkeypatch.setattr("craik.cli_auth_login.capture_and_cache_login", _capture_login)
    monkeypatch.setattr("craik.cli_auth_login.browser_oauth_login", _browser_login)

    result = runner.invoke(
        app,
        ["auth", "login", "openai", "--no-browser", "--json"],
        input="sk-test\n",
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    assert captured == {"provider": "openai", "credential": "sk-test"}


def test_explicit_api_key_mode_overrides_provider_oauth_default(monkeypatch, tmp_path) -> None:
    captured: dict[str, str] = {}

    def _capture_login(provider: str, **kwargs):
        captured["provider"] = provider
        return _capture_result(provider, CredentialKind.KEYRING_REF)

    def _browser_login(provider: str, **kwargs):
        raise AssertionError("explicit api-key mode should not start OAuth")

    monkeypatch.setattr("craik.cli_auth_login.capture_and_cache_login", _capture_login)
    monkeypatch.setattr("craik.cli_auth_login.browser_oauth_login", _browser_login)

    result = runner.invoke(
        app,
        ["auth", "login", "anthropic", "--mode=api-key", "--no-browser", "--json"],
        input="sk-ant-test\n",
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    assert captured == {"provider": "anthropic"}


def _capture_result(provider: str, kind: CredentialKind) -> AuthCaptureResult:
    profile = AuthProfile(
        id=f"{provider}:default",
        kind=kind,
        provider_family=provider,
        metadata={"ref": f"{provider}:default:api-key"},
        created_at=datetime.now(UTC),
    )
    return AuthCaptureResult(
        provider=provider,
        profile=profile,
        status=CredentialStatus(status="ok"),
        credential_storage=CredentialStorageStatus(
            backend="test-keyring",
            status="available",
            secure=True,
        ),
    )
