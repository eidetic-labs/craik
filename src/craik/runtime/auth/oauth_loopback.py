"""Loopback OAuth helpers with PKCE and state validation."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_CALLBACK_PATH = "/oauth/callback"
DEFAULT_CALLBACK_TIMEOUT_SECONDS = 300.0


class OAuthLoopbackError(RuntimeError):
    """Raised when a loopback OAuth callback cannot be completed safely."""


@dataclass(frozen=True)
class PKCEChallenge:
    """PKCE verifier and S256 challenge for one authorization request."""

    verifier: str
    challenge: str
    method: str = "S256"


@dataclass(frozen=True)
class OAuthCallbackResult:
    """Validated OAuth callback parameters."""

    code: str
    state: str
    params: dict[str, str] = field(default_factory=dict)


class OAuthLoopbackListener:
    """One-shot 127.0.0.1 HTTP listener for OAuth authorization callbacks."""

    def __init__(
        self,
        *,
        expected_state: str,
        callback_path: str = DEFAULT_CALLBACK_PATH,
        timeout_seconds: float = DEFAULT_CALLBACK_TIMEOUT_SECONDS,
    ) -> None:
        if not expected_state:
            raise OAuthLoopbackError("OAuth state is required")
        if not callback_path.startswith("/"):
            raise OAuthLoopbackError("OAuth callback path must start with /")
        validate_loopback_host(LOOPBACK_HOST)
        self.expected_state = expected_state
        self.callback_path = callback_path
        self.timeout_seconds = timeout_seconds
        self._event = threading.Event()
        self._result: OAuthCallbackResult | None = None
        self._error: OAuthLoopbackError | None = None
        self._server = HTTPServer(("127.0.0.1", 0), self._handler_class())
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.05},
            daemon=True,
        )

    @property
    def port(self) -> int:
        """Return the assigned ephemeral callback port."""
        return int(self._server.server_address[1])

    @property
    def redirect_uri(self) -> str:
        """Return the full loopback redirect URI for provider authorization."""
        return f"http://{LOOPBACK_HOST}:{self.port}{self.callback_path}"

    def start(self) -> OAuthLoopbackListener:
        """Start accepting one loopback callback."""
        self._thread.start()
        return self

    def wait(self) -> OAuthCallbackResult:
        """Wait for a validated callback or timeout."""
        if not self._event.wait(self.timeout_seconds):
            self.close()
            raise OAuthLoopbackError("OAuth callback timed out")
        self.close()
        if self._error is not None:
            raise self._error
        if self._result is None:
            raise OAuthLoopbackError("OAuth callback did not include a result")
        return self._result

    def close(self) -> None:
        """Stop the listener and release the ephemeral port."""
        self._server.shutdown()
        self._server.server_close()
        if self._thread.is_alive():
            self._thread.join(timeout=2)

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        listener = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                listener._handle_callback(self)

            def log_message(self, format: str, *args: Any) -> None:
                return

        return Handler

    def _handle_callback(self, handler: BaseHTTPRequestHandler) -> None:
        if self._event.is_set():
            _send_text(handler, 410, "OAuth callback already received.")
            return
        parsed = urlparse(handler.path)
        if parsed.path != self.callback_path:
            _send_text(handler, 404, "OAuth callback path not found.")
            return
        query = {
            key: values[-1]
            for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            if values
        }
        received_state = query.get("state", "")
        if not hmac.compare_digest(received_state, self.expected_state):
            self._error = OAuthLoopbackError("OAuth state validation failed")
            self._event.set()
            _send_text(handler, 400, "OAuth state validation failed.")
            return
        code = query.get("code", "")
        if not code:
            self._error = OAuthLoopbackError("OAuth callback missing authorization code")
            self._event.set()
            _send_text(handler, 400, "OAuth callback missing authorization code.")
            return
        self._result = OAuthCallbackResult(code=code, state=received_state, params=query)
        self._event.set()
        _send_text(handler, 200, "OAuth callback received. You can close this window.")


def generate_oauth_state() -> str:
    """Return a high-entropy OAuth state value."""
    return secrets.token_urlsafe(32)


def validate_loopback_host(host: str) -> None:
    """Reject non-loopback OAuth callback bind hosts."""
    if host != LOOPBACK_HOST:
        raise OAuthLoopbackError("OAuth callback host must be 127.0.0.1")


def generate_pkce_challenge() -> PKCEChallenge:
    """Return an RFC 7636 S256 PKCE verifier/challenge pair."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return PKCEChallenge(verifier=verifier, challenge=challenge)


def authorization_url(
    endpoint: str,
    *,
    client_id: str,
    redirect_uri: str,
    scope: list[str],
    state: str,
    pkce: PKCEChallenge,
    extra_params: dict[str, str] | None = None,
) -> str:
    """Build a provider authorization URL using state and PKCE parameters."""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scope),
        "state": state,
        "code_challenge": pkce.challenge,
        "code_challenge_method": pkce.method,
    }
    if extra_params:
        params.update(extra_params)
    separator = "&" if "?" in endpoint else "?"
    return f"{endpoint}{separator}{urlencode(params)}"


def _send_text(handler: BaseHTTPRequestHandler, status: int, message: str) -> None:
    body = message.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
