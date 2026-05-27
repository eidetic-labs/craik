"""Anthropic provider OAuth client primitives."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib import error as url_error
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from craik.runtime.auth.oauth_loopback import (
    PKCEChallenge,
    authorization_url,
    generate_oauth_state,
    generate_pkce_challenge,
)
from craik.runtime.auth.profile import AuthProfile, CredentialKind, CredentialStatus
from craik.runtime.shell import credential_storage

ANTHROPIC_OAUTH_AUTHORIZATION_ENDPOINT = "https://claude.ai/oauth/authorize"
ANTHROPIC_OAUTH_TOKEN_ENDPOINT = "https://console.anthropic.com/v1/oauth/token"  # nosec B105
ANTHROPIC_OAUTH_CLIENT_ID = "craik-cli"
ANTHROPIC_OAUTH_BOOTSTRAP_AUTHORIZATION_ENDPOINT = "https://platform.claude.com/oauth/authorize"
ANTHROPIC_OAUTH_BOOTSTRAP_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
ANTHROPIC_OAUTH_BOOTSTRAP_TOKEN_ENDPOINT = (  # nosec B105
    "https://api.anthropic.com/api/oauth/claude_cli/create_api_key"
)
ANTHROPIC_OAUTH_BOOTSTRAP_OAUTH_TOKEN_ENDPOINT = (  # nosec B105
    "https://console.anthropic.com/v1/oauth/token"
)
ANTHROPIC_OAUTH_SCOPES = ["models.read", "messages.create"]
ANTHROPIC_OAUTH_BOOTSTRAP_SCOPES = [
    "org:create_api_key",
    "user:profile",
    "user:inference",
]
ANTHROPIC_OAUTH_BILLING_SURFACE = "subscription"
ANTHROPIC_OAUTH_BOOTSTRAP_REDIRECT_URI = "https://platform.claude.com/oauth/code/callback"
DEFAULT_TOKEN_TIMEOUT_SECONDS = 10.0

UrlOpen = Callable[..., Any]
BrowserOpener = Callable[[str], bool]
CodePrompt = Callable[[str], str]


class AnthropicOAuthError(RuntimeError):
    """Raised when Anthropic OAuth exchange or storage fails."""


@dataclass(frozen=True)
class AnthropicBootstrapResult:
    """Unsupported Claude Code browser bootstrap result without exposing credential material."""

    api_key: str
    authorization_url: str
    browser_opened: bool


@dataclass(frozen=True)
class AnthropicOAuthTokenSet:
    """Access-token metadata safe to keep outside the refresh operation."""

    access_token: str
    expires_at: datetime
    scope: list[str]
    token_type: str = "Bearer"

    def status(self) -> CredentialStatus:
        """Return an OAuth-specific credential status without token material."""
        return CredentialStatus(status="ok", expires_at=self.expires_at)


@dataclass(frozen=True)
class AnthropicOAuthClient:
    """Minimal Anthropic OAuth authorization-code client."""

    authorization_endpoint: str = ANTHROPIC_OAUTH_AUTHORIZATION_ENDPOINT
    token_endpoint: str = ANTHROPIC_OAUTH_TOKEN_ENDPOINT
    client_id: str = ANTHROPIC_OAUTH_CLIENT_ID
    scope: tuple[str, ...] = tuple(ANTHROPIC_OAUTH_SCOPES)
    timeout_seconds: float = DEFAULT_TOKEN_TIMEOUT_SECONDS

    def authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        pkce: PKCEChallenge,
    ) -> str:
        """Build the browser URL for the Anthropic OAuth authorization request."""
        return authorization_url(
            self.authorization_endpoint,
            client_id=self.client_id,
            redirect_uri=redirect_uri,
            scope=list(self.scope),
            state=state,
            pkce=pkce,
        )

    def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        pkce: PKCEChallenge,
        opener: UrlOpen = urlopen,
        now: datetime | None = None,
    ) -> tuple[AnthropicOAuthTokenSet, str]:
        """Exchange an authorization code for access and refresh tokens."""
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": pkce.verifier,
        }
        return self._post_token(payload, opener=opener, now=now)

    def refresh_access_token(
        self,
        *,
        refresh_token: str,
        opener: UrlOpen = urlopen,
        now: datetime | None = None,
    ) -> tuple[AnthropicOAuthTokenSet, str]:
        """Refresh an expired access token from a stored refresh token."""
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": refresh_token,
        }
        return self._post_token(payload, opener=opener, now=now)

    def _post_token(
        self,
        payload: dict[str, str],
        *,
        opener: UrlOpen,
        now: datetime | None,
    ) -> tuple[AnthropicOAuthTokenSet, str]:
        request = Request(
            self.token_endpoint,
            data=urlencode(payload).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with opener(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            raise AnthropicOAuthError("Anthropic OAuth token request timed out") from exc
        except url_error.HTTPError as exc:
            raise AnthropicOAuthError(
                _oauth_http_error_detail("Anthropic OAuth token request failed", exc)
            ) from exc
        except OSError as exc:
            raise AnthropicOAuthError("Anthropic OAuth token request failed") from exc
        except json.JSONDecodeError as exc:
            raise AnthropicOAuthError("Anthropic OAuth token response was invalid") from exc
        if not isinstance(data, dict):
            raise AnthropicOAuthError("Anthropic OAuth token response was invalid")
        return _token_set_from_response(data, scope=list(self.scope), now=now)


def bootstrap_anthropic_api_key(
    *,
    browser_opener: BrowserOpener,
    code_prompt: CodePrompt,
    opener: UrlOpen = urlopen,
) -> AnthropicBootstrapResult:
    """Run Anthropic's unsupported Claude Code browser bootstrap and return the credential."""
    pkce = generate_pkce_challenge()
    authorization = _bootstrap_authorization_url(
        redirect_uri=ANTHROPIC_OAUTH_BOOTSTRAP_REDIRECT_URI,
        state=generate_oauth_state(),
        pkce=pkce,
    )
    browser_opened = browser_opener(authorization)
    code = _normalize_one_time_code(code_prompt("Anthropic one-time code"))
    if not code:
        raise AnthropicOAuthError("Anthropic Claude Code bootstrap requires a one-time code")
    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": ANTHROPIC_OAUTH_BOOTSTRAP_REDIRECT_URI,
        "code_verifier": pkce.verifier,
        "scope": " ".join(ANTHROPIC_OAUTH_BOOTSTRAP_SCOPES),
    }
    if ANTHROPIC_OAUTH_BOOTSTRAP_CLIENT_ID:
        token_payload["client_id"] = ANTHROPIC_OAUTH_BOOTSTRAP_CLIENT_ID
    access_token = _exchange_bootstrap_code_for_access_token(
        token_payload,
        opener=opener,
    )
    payload = _create_bootstrap_api_key(access_token, opener=opener)
    api_key = payload.get("api_key") or payload.get("key") or payload.get("access_token")
    if not isinstance(api_key, str) or not api_key:
        raise AnthropicOAuthError(
            "Anthropic Claude Code bootstrap returned no credential. "
            "Re-run: craik auth login anthropic"
        )
    return AnthropicBootstrapResult(
        api_key=api_key,
        authorization_url=authorization,
        browser_opened=browser_opened,
    )


def _exchange_bootstrap_code_for_access_token(
    payload: dict[str, str],
    *,
    opener: UrlOpen,
) -> str:
    request = Request(
        ANTHROPIC_OAUTH_BOOTSTRAP_OAUTH_TOKEN_ENDPOINT,
        data=urlencode(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=DEFAULT_TOKEN_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except TimeoutError as exc:
        raise AnthropicOAuthError(
            "Anthropic Claude Code bootstrap token request timed out"
        ) from exc
    except url_error.HTTPError as exc:
        raise AnthropicOAuthError(
            _oauth_http_error_detail("Anthropic Claude Code bootstrap token request failed", exc)
        ) from exc
    except OSError as exc:
        raise AnthropicOAuthError("Anthropic Claude Code bootstrap token request failed") from exc
    except json.JSONDecodeError as exc:
        raise AnthropicOAuthError(
            "Anthropic Claude Code bootstrap token response was invalid"
        ) from exc
    if not isinstance(payload, dict):
        raise AnthropicOAuthError("Anthropic Claude Code bootstrap token response was invalid")
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise AnthropicOAuthError(
            "Anthropic Claude Code bootstrap token response returned no access token. "
            "Re-run: craik auth login anthropic"
        )
    return access_token


def _create_bootstrap_api_key(
    access_token: str,
    *,
    opener: UrlOpen,
) -> dict[str, Any]:
    request = Request(
        ANTHROPIC_OAUTH_BOOTSTRAP_TOKEN_ENDPOINT,
        data=json.dumps({}).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=DEFAULT_TOKEN_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except TimeoutError as exc:
        raise AnthropicOAuthError(
            "Anthropic Claude Code credential creation request timed out"
        ) from exc
    except url_error.HTTPError as exc:
        raise AnthropicOAuthError(
            _oauth_http_error_detail(
                "Anthropic Claude Code credential creation request failed",
                exc,
            )
        ) from exc
    except OSError as exc:
        raise AnthropicOAuthError(
            "Anthropic Claude Code credential creation request failed"
        ) from exc
    except json.JSONDecodeError as exc:
        raise AnthropicOAuthError(
            "Anthropic Claude Code credential creation response was invalid"
        ) from exc
    if not isinstance(payload, dict):
        raise AnthropicOAuthError("Anthropic Claude Code credential creation response was invalid")
    return payload


def _bootstrap_authorization_url(
    *,
    redirect_uri: str,
    state: str,
    pkce: PKCEChallenge,
) -> str:
    params = {
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": pkce.challenge,
        "code_challenge_method": pkce.method,
        "scope": " ".join(ANTHROPIC_OAUTH_BOOTSTRAP_SCOPES),
    }
    if ANTHROPIC_OAUTH_BOOTSTRAP_CLIENT_ID:
        params["client_id"] = ANTHROPIC_OAUTH_BOOTSTRAP_CLIENT_ID
    return f"{ANTHROPIC_OAUTH_BOOTSTRAP_AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


def _normalize_one_time_code(raw_code: str) -> str:
    """Accept either the displayed one-time code or a pasted callback URL."""
    code = raw_code.strip()
    if not code:
        return ""
    if "://" in code:
        parsed = urlparse(code)
        params = parse_qs(parsed.query)
        if params.get("code"):
            return params["code"][0].strip()
    if code.startswith("code="):
        params = parse_qs(code)
        if params.get("code"):
            return params["code"][0].strip()
    if "#" in code:
        return code.split("#", 1)[0].strip()
    return code


def _oauth_http_error_detail(prefix: str, exc: url_error.HTTPError) -> str:
    detail = _safe_oauth_error_payload(exc)
    if detail:
        return f"{prefix}: HTTP {exc.code}: {detail}"
    return f"{prefix}: HTTP {exc.code}"


def _safe_oauth_error_payload(exc: url_error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    if not raw.strip():
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return _truncate_oauth_error(raw)
    if not isinstance(payload, dict):
        return _truncate_oauth_error(raw)
    parts: list[str] = []
    for key in ("error", "error_description", "message", "detail"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(f"{key}={_truncate_oauth_error(value)}")
    return "; ".join(parts) if parts else _truncate_oauth_error(raw)


def _truncate_oauth_error(value: str) -> str:
    compact = " ".join(value.strip().split())
    return compact[:300]


def store_anthropic_oauth_profile(
    token_set: AnthropicOAuthTokenSet,
    refresh_token: str,
    *,
    profile_id: str = "anthropic:subscription",
    env: dict[str, str] | None = None,
) -> AuthProfile:
    """Store Anthropic OAuth tokens in secure credential storage and return a profile."""
    status = credential_storage.credential_storage_status(env)
    if status.status != "available" or not status.secure:
        raise AnthropicOAuthError("Anthropic OAuth token storage requires an OS keyring backend")

    token_handle = f"{profile_id}:oauth-access-token"
    refresh_handle = f"{profile_id}:oauth-refresh-token"
    credential_storage.put_cached_credential(token_handle, token_set.access_token, env=env)
    credential_storage.put_cached_credential(refresh_handle, refresh_token, env=env)
    return AuthProfile(
        id=profile_id,
        kind=CredentialKind.OAUTH,
        provider_family="anthropic",
        metadata={
            "source": "provider-oauth",
            "provider": "anthropic",
            "credential_backend": status.backend,
            "billing_surface": ANTHROPIC_OAUTH_BILLING_SURFACE,
            "token_expires_at": token_set.expires_at.isoformat(),
            "token_type": token_set.token_type,
        },
        created_at=datetime.now(UTC),
        last_status="ok",
        oauth_authorization_endpoint=ANTHROPIC_OAUTH_AUTHORIZATION_ENDPOINT,
        oauth_token_endpoint=ANTHROPIC_OAUTH_TOKEN_ENDPOINT,
        oauth_client_id=ANTHROPIC_OAUTH_CLIENT_ID,
        oauth_scope_list=token_set.scope,
        oauth_token_keyring_handle=token_handle,
        oauth_refresh_keyring_handle=refresh_handle,
    )


def _token_set_from_response(
    payload: dict[str, Any],
    *,
    scope: list[str],
    now: datetime | None,
) -> tuple[AnthropicOAuthTokenSet, str]:
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    token_type = payload.get("token_type", "Bearer")
    if not isinstance(access_token, str) or not access_token:
        raise AnthropicOAuthError("Anthropic OAuth token response missing access token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise AnthropicOAuthError("Anthropic OAuth token response missing refresh token")
    if not isinstance(token_type, str) or not token_type:
        token_type = "Bearer"  # nosec B105
    expires_in = _expires_in(payload.get("expires_in"))
    response_scope = _scope(payload.get("scope"), fallback=scope)
    issued_at = now or datetime.now(UTC)
    token_set = AnthropicOAuthTokenSet(
        access_token=access_token,
        expires_at=issued_at + timedelta(seconds=expires_in),
        scope=response_scope,
        token_type=token_type,
    )
    return token_set, refresh_token


def _expires_in(value: Any) -> int:
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return 3600


def _scope(value: Any, *, fallback: list[str]) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [item for item in value.split() if item]
    if isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value):
        return list(value)
    return fallback


__all__ = [
    "ANTHROPIC_OAUTH_AUTHORIZATION_ENDPOINT",
    "ANTHROPIC_OAUTH_BILLING_SURFACE",
    "ANTHROPIC_OAUTH_BOOTSTRAP_AUTHORIZATION_ENDPOINT",
    "ANTHROPIC_OAUTH_BOOTSTRAP_CLIENT_ID",
    "ANTHROPIC_OAUTH_BOOTSTRAP_OAUTH_TOKEN_ENDPOINT",
    "ANTHROPIC_OAUTH_BOOTSTRAP_REDIRECT_URI",
    "ANTHROPIC_OAUTH_BOOTSTRAP_SCOPES",
    "ANTHROPIC_OAUTH_BOOTSTRAP_TOKEN_ENDPOINT",
    "ANTHROPIC_OAUTH_CLIENT_ID",
    "ANTHROPIC_OAUTH_SCOPES",
    "ANTHROPIC_OAUTH_TOKEN_ENDPOINT",
    "AnthropicBootstrapResult",
    "AnthropicOAuthClient",
    "AnthropicOAuthError",
    "AnthropicOAuthTokenSet",
    "bootstrap_anthropic_api_key",
    "store_anthropic_oauth_profile",
]
