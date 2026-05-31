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


def test_anthropic_defaults_to_oauth_cli_delegation_when_mode_is_omitted(
    monkeypatch,
    tmp_path,
) -> None:
    called: dict[str, str] = {}

    def _claude_cli_login(**kwargs):
        called["provider"] = "anthropic"
        return OAuthLoginResult(
            capture=_capture_result("anthropic", CredentialKind.MARKER),
            authorization_url="claude",
            browser_opened=False,
        )

    monkeypatch.setattr("craik.cli_auth_login.anthropic_claude_cli_login", _claude_cli_login)

    result = runner.invoke(
        app,
        ["auth", "login", "anthropic", "--json"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    assert called == {"provider": "anthropic"}
    assert json.loads(result.stdout)["kind"] == "marker"
    assert json.loads(result.stdout)["mode"] == "oauth"
    assert json.loads(result.stdout)["auth_transport"] == "claude-cli"
    assert json.loads(result.stdout)["authorization_url"] == "claude"


def test_anthropic_explicit_oauth_mode_uses_cli_delegation(
    monkeypatch,
    tmp_path,
) -> None:
    called: dict[str, str] = {}

    def _claude_cli_login(**kwargs):
        called["provider"] = "anthropic"
        called["profile_id"] = str(kwargs["profile_id"])
        return OAuthLoginResult(
            capture=_capture_result("anthropic", CredentialKind.MARKER),
            authorization_url="claude",
            browser_opened=False,
        )

    monkeypatch.setattr("craik.cli_auth_login.anthropic_claude_cli_login", _claude_cli_login)

    result = runner.invoke(
        app,
        ["auth", "login", "anthropic", "--mode=oauth", "--json"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    assert called == {"provider": "anthropic", "profile_id": "None"}
    assert json.loads(result.stdout)["mode"] == "oauth"
    assert json.loads(result.stdout)["auth_transport"] == "claude-cli"


def test_anthropic_claude_cli_mode_is_not_public(tmp_path) -> None:
    result = runner.invoke(
        app,
        ["auth", "login", "anthropic", "--mode=claude-cli", "--json"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code != 0
    assert "api-key or oauth" in result.output


def test_google_defaults_to_oauth_when_mode_is_omitted(monkeypatch, tmp_path) -> None:
    called: dict[str, bool] = {}

    def _google_login(**kwargs):
        called["google"] = True
        return OAuthLoginResult(
            capture=_capture_result("google", CredentialKind.KEYRING_REF),
            authorization_url="gcloud auth application-default login",
            browser_opened=False,
        )

    monkeypatch.setattr("craik.cli_auth_login.google_oauth_login", _google_login)

    result = runner.invoke(
        app,
        ["auth", "login", "google", "--json"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    assert called == {"google": True}
    assert json.loads(result.stdout)["authorization_url"] == "gcloud auth application-default login"


def test_gemini_alias_defaults_to_oauth_when_mode_is_omitted(monkeypatch, tmp_path) -> None:
    called: dict[str, bool] = {}

    def _google_login(**kwargs):
        called["google"] = True
        return OAuthLoginResult(
            capture=_capture_result("google", CredentialKind.KEYRING_REF),
            authorization_url="gcloud auth application-default login",
            browser_opened=False,
        )

    monkeypatch.setattr("craik.cli_auth_login.google_oauth_login", _google_login)

    result = runner.invoke(
        app,
        ["auth", "login", "gemini", "--json"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    assert called == {"google": True}
    assert json.loads(result.stdout)["authorization_url"] == "gcloud auth application-default login"


def test_google_oauth_accepts_project_id_and_service_account(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    def _google_login(**kwargs):
        captured.update(kwargs)
        return OAuthLoginResult(
            capture=_capture_result("google", CredentialKind.KEYRING_REF),
            authorization_url="gcloud auth application-default login",
            browser_opened=False,
        )

    monkeypatch.setattr("craik.cli_auth_login.google_oauth_login", _google_login)
    sa_path = tmp_path / "sa.json"
    sa_path.write_text("{}", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "auth",
            "login",
            "gemini",
            "--mode=oauth",
            "--project-id=proj-1",
            f"--service-account={sa_path}",
            "--json",
        ],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    assert captured["project_id"] == "proj-1"
    assert str(captured["service_account_path"]) == str(sa_path)


def test_auth_login_help_advertises_google_provider() -> None:
    result = runner.invoke(app, ["auth", "login", "--help"])

    assert result.exit_code == 0, result.output
    assert "google" in result.output
    assert "openai, anthropic, gemini, or local" not in result.output


def test_openai_defaults_to_oauth_when_mode_is_omitted_without_api_key(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    called: dict[str, str] = {}

    def _browser_login(provider: str, **kwargs):
        called["provider"] = provider
        return OAuthLoginResult(
            capture=_capture_result(provider, CredentialKind.OAUTH),
            authorization_url="https://auth.openai.com/oauth/authorize",
            browser_opened=False,
        )

    monkeypatch.setattr("craik.cli_auth_login.browser_oauth_login", _browser_login)

    result = runner.invoke(
        app,
        ["auth", "login", "openai", "--json"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0, result.output
    assert called == {"provider": "openai"}
    assert json.loads(result.stdout)["kind"] == "oauth"


def test_openai_no_browser_defaults_to_api_key_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    captured: dict[str, str] = {}

    def _capture_login(provider: str, **kwargs):
        captured["provider"] = provider
        captured["credential"] = kwargs["credential"]
        return _capture_result(provider, CredentialKind.KEYRING_REF)

    def _browser_login(provider: str, **kwargs):
        raise AssertionError("OpenAI --no-browser should use api-key mode by default")

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


def test_openai_defaults_to_api_key_when_openai_api_key_is_set(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    captured: dict[str, str] = {}

    def _capture_login(provider: str, **kwargs):
        captured["provider"] = provider
        captured["credential"] = kwargs["credential"]
        return _capture_result(provider, CredentialKind.KEYRING_REF)

    def _browser_login(provider: str, **kwargs):
        raise AssertionError("OpenAI should use api-key mode when OPENAI_API_KEY is set")

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
    oauth_fields = (
        {
            "oauth_authorization_endpoint": f"https://auth.{provider}.example/authorize",
            "oauth_token_endpoint": f"https://auth.{provider}.example/token",
            "oauth_client_id": "test-client",
            "oauth_scope_list": ["openid"],
            "oauth_token_keyring_handle": f"{provider}:default:access",
            "oauth_refresh_keyring_handle": f"{provider}:default:refresh",
        }
        if kind is CredentialKind.OAUTH
        else {}
    )
    profile = AuthProfile(
        id=f"{provider}:default",
        kind=kind,
        provider_family=provider,
        metadata={"ref": f"{provider}:default:api-key"},
        created_at=datetime.now(UTC),
        **oauth_fields,
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
