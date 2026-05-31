"""Browser OAuth provider login orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from craik.runtime.auth.guided_setup import default_pool_for_profile
from craik.runtime.auth.login import AuthCaptureResult
from craik.runtime.auth.oauth_loopback import (
    OAuthLoopbackListener,
    generate_oauth_state,
    generate_pkce_challenge,
)
from craik.runtime.auth.pool import CredentialPool
from craik.runtime.auth.profile import AuthProfile
from craik.runtime.auth.sources.anthropic_claude_cli import (
    create_claude_cli_profile,
)
from craik.runtime.auth.sources.anthropic_oauth import (
    AnthropicOAuthClient,
    AnthropicOAuthError,
    store_anthropic_oauth_profile,
)
from craik.runtime.auth.sources.google_oauth import (
    store_google_adc_profile,
    store_google_service_account_profile,
)
from craik.runtime.auth.sources.openai_oauth import (
    OPENAI_OAUTH_REDIRECT_PATH,
    OPENAI_OAUTH_REDIRECT_PORT,
    OpenAIOAuthClient,
    OpenAIOAuthError,
    store_openai_oauth_profile,
)
from craik.runtime.auth.store import AuthProfileStore
from craik.runtime.providers.provider_transport import normalize_provider_family
from craik.runtime.shell.credential_storage import (
    CredentialStorageStatus,
    credential_storage_status,
)

BrowserOpener = Callable[[str], bool]
CodePrompt = Callable[[str], str]


@dataclass(frozen=True)
class OAuthLoginResult:
    """Redacted result for one browser OAuth provider login."""

    capture: AuthCaptureResult
    authorization_url: str
    browser_opened: bool

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe payload without token material."""
        return self.capture.as_dict() | {
            "authorization_url": self.authorization_url,
            "browser_opened": self.browser_opened,
            "copy_paste_fallback": True,
        }


def browser_oauth_login(
    provider: str,
    *,
    profile_id: str | None = None,
    project_id: str | None = None,
    browser_opener: BrowserOpener,
    code_prompt: CodePrompt | None = None,
    env: dict[str, str] | None = None,
) -> OAuthLoginResult:
    """Create a provider OAuth profile through a loopback browser login."""
    normalized = normalize_provider_family(provider.strip().lower())
    if normalized == "anthropic":
        raise AnthropicOAuthError(
            "Anthropic browser OAuth login is not supported. Use Claude CLI delegation "
            "or a Console API key."
        )
    if normalized == "google":
        return google_oauth_login(
            profile_id=profile_id,
            project_id=project_id,
            service_account_path=None,
            env=env,
        )
    state = generate_oauth_state()
    pkce = generate_pkce_challenge()
    listener = _loopback_listener(normalized, state)
    try:
        client = _oauth_client(normalized)
        authorization = client.authorization_url(
            redirect_uri=listener.redirect_uri,
            state=state,
            pkce=pkce,
        )
        browser_opened = browser_opener(authorization)
        callback = listener.wait()
        token_set, refresh_token = client.exchange_code(
            code=callback.code,
            redirect_uri=listener.redirect_uri,
            pkce=pkce,
        )
    finally:
        listener.close()

    profile = _store_oauth_profile(
        normalized,
        token_set,
        refresh_token,
        profile_id=profile_id,
        env=env,
    )
    AuthProfileStore.from_env(env).put(profile)
    CredentialPool.from_env(env).put(default_pool_for_profile(profile))
    capture = AuthCaptureResult(
        provider=normalized,
        profile=profile,
        status=token_set.status(),
        credential_storage=credential_storage_status(env),
    )
    return OAuthLoginResult(
        capture=capture,
        authorization_url=authorization,
        browser_opened=browser_opened,
    )


def _loopback_listener(provider: str, state: str) -> OAuthLoopbackListener:
    try:
        if provider == "openai":
            return OAuthLoopbackListener(
                expected_state=state,
                callback_path=OPENAI_OAUTH_REDIRECT_PATH,
                port=OPENAI_OAUTH_REDIRECT_PORT,
            ).start()
        return OAuthLoopbackListener(expected_state=state).start()
    except OSError as exc:
        if provider == "openai":
            raise OpenAIOAuthError(
                "OpenAI OAuth callback port 1455 is in use. Close any in-flight "
                "OpenAI OAuth authentication and retry."
            ) from exc
        raise


def anthropic_claude_cli_login(
    *,
    profile_id: str | None = None,
    env: dict[str, str] | None = None,
) -> OAuthLoginResult:
    """Create an Anthropic marker profile delegated to local Claude CLI auth."""
    target_profile_id = profile_id or "anthropic:default"
    result = create_claude_cli_profile(profile_id=target_profile_id)
    AuthProfileStore.from_env(env).put(result.profile)
    CredentialPool.from_env(env).put(default_pool_for_profile(result.profile))
    capture = AuthCaptureResult(
        provider="anthropic",
        profile=result.profile,
        status=result.status,
        credential_storage=CredentialStorageStatus(
            backend=result.credential_storage_backend,
            status="available",
            secure=True,
        ),
    )
    return OAuthLoginResult(
        capture=capture,
        authorization_url="claude auth login",
        browser_opened=False,
    )


def _default_token_prompt(prompt: str) -> str:
    return input(prompt)


def google_oauth_login(
    *,
    profile_id: str | None = None,
    project_id: str | None = None,
    service_account_path: Path | None = None,
    env: dict[str, str] | None = None,
) -> OAuthLoginResult:
    """Create a Gemini OAuth profile via ADC or a service-account JSON file."""
    if service_account_path is not None:
        result = store_google_service_account_profile(
            json_path=service_account_path,
            profile_id=profile_id or "gemini:vertex",
            env=env,
        )
    else:
        result = store_google_adc_profile(
            profile_id=profile_id or "gemini:vertex",
            project_id=project_id,
            env=env,
        )
    capture = AuthCaptureResult(
        provider="gemini",
        profile=result.profile,
        status=result.status(),
        credential_storage=credential_storage_status(env),
    )
    return OAuthLoginResult(
        capture=capture,
        authorization_url="gcloud auth application-default login",
        browser_opened=False,
    )


def _oauth_client(provider: str) -> OpenAIOAuthClient | AnthropicOAuthClient:
    if provider == "openai":
        return OpenAIOAuthClient()
    if provider == "anthropic":
        return AnthropicOAuthClient()
    raise ValueError("provider loopback OAuth login supports openai or anthropic")


def _store_oauth_profile(
    provider: str,
    token_set: Any,
    refresh_token: str,
    *,
    profile_id: str | None,
    env: dict[str, str] | None,
) -> AuthProfile:
    if provider == "openai":
        return store_openai_oauth_profile(
            token_set,
            refresh_token,
            profile_id=profile_id or "openai:subscription",
            env=env,
        )
    if provider == "anthropic":
        return store_anthropic_oauth_profile(
            token_set,
            refresh_token,
            profile_id=profile_id or "anthropic:subscription",
            env=env,
        )
    raise ValueError("provider loopback OAuth login supports openai or anthropic")


# Deprecated alias; use google_oauth_login (gemini→google rename).
gemini_oauth_login = google_oauth_login


__all__ = [
    "OAuthLoginResult",
    "anthropic_claude_cli_login",
    "browser_oauth_login",
    "gemini_oauth_login",
    "google_oauth_login",
]
