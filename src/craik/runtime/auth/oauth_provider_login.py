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
from craik.runtime.auth.sources.anthropic_oauth import (
    AnthropicOAuthClient,
    store_anthropic_oauth_profile,
)
from craik.runtime.auth.sources.gemini_oauth import (
    store_gemini_adc_profile,
    store_gemini_service_account_profile,
)
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
    if normalized == "gemini":
        return gemini_oauth_login(
            profile_id=profile_id,
            project_id=project_id,
            service_account_path=None,
            env=env,
        )
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


def gemini_oauth_login(
    *,
    profile_id: str | None = None,
    project_id: str | None = None,
    service_account_path: Path | None = None,
    env: dict[str, str] | None = None,
) -> OAuthLoginResult:
    """Create a Gemini OAuth profile via ADC or a service-account JSON file."""
    if service_account_path is not None:
        result = store_gemini_service_account_profile(
            json_path=service_account_path,
            profile_id=profile_id or "gemini:vertex",
            env=env,
        )
    else:
        result = store_gemini_adc_profile(
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


__all__ = ["OAuthLoginResult", "browser_oauth_login", "gemini_oauth_login"]
