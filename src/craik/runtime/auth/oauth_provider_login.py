"""Browser OAuth provider login orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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
from craik.runtime.auth.sources.anthropic_oauth import (
    AnthropicOAuthClient,
    store_anthropic_oauth_profile,
)
from craik.runtime.auth.sources.gemini_oauth import GeminiOAuthClient, store_gemini_oauth_profile
from craik.runtime.auth.sources.openai_oauth import OpenAIOAuthClient, store_openai_oauth_profile
from craik.runtime.auth.store import AuthProfileStore
from craik.runtime.shell.credential_storage import credential_storage_status

BrowserOpener = Callable[[str], bool]


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
    env: dict[str, str] | None = None,
) -> OAuthLoginResult:
    """Create a provider OAuth profile through a loopback browser login."""
    normalized = provider.strip().lower()
    state = generate_oauth_state()
    pkce = generate_pkce_challenge()
    listener = OAuthLoopbackListener(expected_state=state).start()
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
        project_id=project_id,
        env=env,
    )
    AuthProfileStore.from_env(env).put(profile)
    CredentialPool.from_env().put(default_pool_for_profile(profile))
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


def _oauth_client(provider: str) -> OpenAIOAuthClient | AnthropicOAuthClient | GeminiOAuthClient:
    if provider == "openai":
        return OpenAIOAuthClient()
    if provider == "anthropic":
        return AnthropicOAuthClient()
    if provider == "gemini":
        return GeminiOAuthClient()
    raise ValueError("provider OAuth login supports openai, anthropic, or gemini")


def _store_oauth_profile(
    provider: str,
    token_set: Any,
    refresh_token: str,
    *,
    profile_id: str | None,
    project_id: str | None,
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
    if provider == "gemini":
        return store_gemini_oauth_profile(
            token_set,
            refresh_token,
            profile_id=profile_id or "gemini:vertex",
            project_id=project_id,
            env=env,
        )
    raise ValueError("provider OAuth login supports openai, anthropic, or gemini")


__all__ = ["OAuthLoginResult", "browser_oauth_login"]
