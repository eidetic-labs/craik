"""OIDC operator authentication and ID token validation."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib import error, parse, request

from pydantic import Field, model_validator

from craik.contracts.models import CraikModel
from craik.runtime.auth.operator.cache_control import cache_control_ttl_seconds
from craik.runtime.auth.operator.session import OperatorSession
from craik.runtime.auth.url_safety import require_https_url

DEFAULT_DISCOVERY_TTL_SECONDS = 3600
DEFAULT_CLOCK_SKEW_SECONDS = 60
SUPPORTED_ID_TOKEN_ALGORITHMS = frozenset({"HS256", "RS256"})
RSA_SHA256_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")


class OIDCAuthenticationError(RuntimeError):
    """Raised when OIDC authentication or token validation fails."""


class OIDCConfig(CraikModel):
    """OIDC client configuration for an operator identity provider."""

    issuer: str
    client_id: str
    client_secret_ref: str | None = None
    scopes: list[str] = Field(default_factory=lambda: ["openid", "profile", "email"])
    audience: str | None = None
    groups_claim: str = "groups"
    oidc_allow_loopback_http: bool = False
    allowed_id_token_algorithms: list[str] = Field(default_factory=lambda: ["RS256", "HS256"])

    @model_validator(mode="after")
    def validate_oidc_endpoints(self) -> OIDCConfig:
        """Reject non-HTTPS issuers unless loopback HTTP was explicitly allowed."""
        require_https_url(
            self.issuer,
            allow_loopback_http=self.oidc_allow_loopback_http,
            error_type=OIDCAuthenticationError,
        )
        algorithms = set(self.allowed_id_token_algorithms)
        if not algorithms:
            raise OIDCAuthenticationError("OIDC ID token algorithm allowlist cannot be empty")
        if "none" in algorithms or not algorithms.issubset(SUPPORTED_ID_TOKEN_ALGORITHMS):
            raise OIDCAuthenticationError("OIDC ID token algorithm allowlist is unsupported")
        return self


@dataclass
class OIDCAuthenticator:
    """Authenticate operators through a configured OIDC provider."""

    config: OIDCConfig
    timeout_seconds: float = 5.0
    discovery_ttl_seconds: int = DEFAULT_DISCOVERY_TTL_SECONDS
    clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS
    _discovery: dict[str, Any] | None = field(default=None, init=False)
    _discovery_expires_at: float = field(default=0.0, init=False)
    _jwks: dict[str, Any] | None = field(default=None, init=False)
    _jwks_expires_at: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        """Validate endpoint posture before any network request is made."""
        require_https_url(
            self.config.issuer,
            allow_loopback_http=self.config.oidc_allow_loopback_http,
            error_type=OIDCAuthenticationError,
        )

    def device_authorization(self) -> dict[str, Any]:
        """Start RFC 8628 device-code authorization."""
        endpoint = self._discovery_endpoint("device_authorization_endpoint")
        payload = {
            "client_id": self.config.client_id,
            "scope": " ".join(self.config.scopes),
        }
        if self.config.audience:
            payload["audience"] = self.config.audience
        return self._post_form(endpoint, payload)

    def poll_device_token(
        self,
        device_code: str,
        *,
        interval_seconds: int = 5,
        max_wait_seconds: int = 600,
    ) -> OperatorSession:
        """Poll the token endpoint until the device-code flow completes."""
        return self.session_from_token_response(
            self.poll_device_token_response(
                device_code,
                interval_seconds=interval_seconds,
                max_wait_seconds=max_wait_seconds,
            )
        )

    def poll_device_token_response(
        self,
        device_code: str,
        *,
        interval_seconds: int = 5,
        max_wait_seconds: int = 600,
    ) -> dict[str, Any]:
        """Poll the token endpoint until it returns a token response payload."""
        endpoint = self._discovery_endpoint("token_endpoint")
        deadline = time.monotonic() + max_wait_seconds
        interval = max(1, interval_seconds)
        while time.monotonic() <= deadline:
            payload = {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": self.config.client_id,
            }
            response = self._post_form(endpoint, payload, allow_oauth_error=True)
            if "id_token" in response:
                return response
            oauth_error = response.get("error")
            if oauth_error == "authorization_pending":
                time.sleep(interval)
                continue
            if oauth_error == "slow_down":
                interval += 5
                time.sleep(interval)
                continue
            raise OIDCAuthenticationError("device-code authorization failed")
        raise OIDCAuthenticationError("device-code authorization timed out")

    def loopback_authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str | None = None,
        code_verifier: str | None = None,
    ) -> tuple[str, str, str]:
        """Build a loopback authorization URL with PKCE parameters."""
        verifier = code_verifier or _pkce_verifier()
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        session_state = state or secrets.token_urlsafe(24)
        endpoint = self._discovery_endpoint("authorization_endpoint")
        query = parse.urlencode(
            {
                "response_type": "code",
                "client_id": self.config.client_id,
                "redirect_uri": redirect_uri,
                "scope": " ".join(self.config.scopes),
                "state": session_state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{endpoint}?{query}", verifier, session_state

    def exchange_authorization_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
        expected_state: str,
        received_state: str | None,
    ) -> OperatorSession:
        """Exchange a loopback authorization code for an operator session."""
        _validate_authorization_state(expected_state, received_state)
        endpoint = self._discovery_endpoint("token_endpoint")
        response = self._post_form(
            endpoint,
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": self.config.client_id,
                "code_verifier": code_verifier,
            },
        )
        return self.session_from_token_response(response)

    def session_from_token_response(self, payload: dict[str, Any]) -> OperatorSession:
        """Validate an ID token response and return a normalized session."""
        session, _refresh_token = self.session_and_refresh_from_token_response(payload)
        return session

    def session_and_refresh_from_token_response(
        self,
        payload: dict[str, Any],
    ) -> tuple[OperatorSession, str | None]:
        """Validate an ID token response and return the session plus refresh token."""
        id_token = payload.get("id_token")
        if not isinstance(id_token, str):
            raise OIDCAuthenticationError("OIDC token response did not include an ID token")
        claims = self.validate_id_token(id_token)
        refresh_token = payload.get("refresh_token")
        refresh_token = refresh_token if isinstance(refresh_token, str) and refresh_token else None
        session = OperatorSession(
            subject=_required_string(claims, "sub"),
            email=_optional_string(claims, "email"),
            display_name=_optional_string(claims, "name"),
            groups=_groups_from_claim(claims.get(self.config.groups_claim)),
            issuer=_required_string(claims, "iss"),
            id_token_jti=_token_identifier(claims),
            expires_at=_timestamp_claim(claims, "exp"),
            refresh_token_ref="operator-session.refresh_token" if refresh_token else None,
            dashboard_binding_token=secrets.token_urlsafe(32),
        )
        return session, refresh_token

    def refresh_session(self, refresh_token: str) -> tuple[OperatorSession, str | None]:
        """Refresh an operator session with a stored refresh token."""
        endpoint = self._discovery_endpoint("token_endpoint")
        response = self._post_form(
            endpoint,
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.config.client_id,
            },
        )
        session, new_refresh_token = self.session_and_refresh_from_token_response(response)
        return session, new_refresh_token or refresh_token

    def revoke_refresh_token(self, refresh_token: str) -> bool:
        """Best-effort refresh-token revocation."""
        endpoint = self.discovery().get("revocation_endpoint")
        if not isinstance(endpoint, str) or not endpoint:
            return False
        endpoint = self._require_endpoint_url(endpoint)
        try:
            self._post_form(
                endpoint,
                {
                    "token": refresh_token,
                    "token_type_hint": "refresh_token",
                    "client_id": self.config.client_id,
                },
                allow_oauth_error=True,
            )
        except OIDCAuthenticationError:
            return False
        return True

    def validate_id_token(self, token: str) -> dict[str, Any]:
        """Validate an OIDC ID token against discovery metadata and JWKS."""
        header, claims, signing_input, signature = _decode_jwt(token)
        alg = _required_string(header, "alg")
        if alg == "none":
            raise OIDCAuthenticationError("OIDC ID token uses an unsupported algorithm")
        if alg not in self.config.allowed_id_token_algorithms:
            raise OIDCAuthenticationError("OIDC ID token algorithm is not allowed")
        kid = _required_string(header, "kid")
        key = self._jwk_for_kid(kid)
        _verify_signature(alg, key, signing_input, signature)
        self._validate_claims(claims)
        return claims

    def discovery(self) -> dict[str, Any]:
        """Return cached OIDC discovery metadata."""
        now = time.monotonic()
        if self._discovery is not None and now < self._discovery_expires_at:
            return self._discovery
        url = self.config.issuer.rstrip("/") + "/.well-known/openid-configuration"
        url = self._require_endpoint_url(url)
        payload = self._get_json(url)
        issuer = payload.get("issuer")
        if issuer != self.config.issuer.rstrip("/"):
            raise OIDCAuthenticationError("OIDC discovery issuer did not match configuration")
        self._discovery = payload
        self._discovery_expires_at = now + self.discovery_ttl_seconds
        return payload

    def jwks(self) -> dict[str, Any]:
        """Return cached JWKS metadata."""
        now = time.monotonic()
        if self._jwks is not None and now < self._jwks_expires_at:
            return self._jwks
        payload, headers = self._get_json_with_headers(self._discovery_endpoint("jwks_uri"))
        keys = payload.get("keys")
        if not isinstance(keys, list):
            raise OIDCAuthenticationError("OIDC JWKS did not contain keys")
        self._jwks = payload
        self._jwks_expires_at = now + cache_control_ttl_seconds(
            headers,
            self.discovery_ttl_seconds,
        )
        return payload

    def _validate_claims(self, claims: dict[str, Any]) -> None:
        if claims.get("iss") != self.config.issuer.rstrip("/"):
            raise OIDCAuthenticationError("OIDC ID token issuer did not match configuration")
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        if self.config.client_id not in audiences and self.config.audience not in audiences:
            raise OIDCAuthenticationError("OIDC ID token audience did not match configuration")
        now = datetime.now(UTC)
        skew = timedelta(seconds=self.clock_skew_seconds)
        if _timestamp_claim(claims, "exp") < now - skew:
            raise OIDCAuthenticationError("OIDC ID token is expired")
        nbf = _optional_timestamp_claim(claims, "nbf")
        if nbf is not None and nbf > now + skew:
            raise OIDCAuthenticationError("OIDC ID token is not yet valid")
        iat = _optional_timestamp_claim(claims, "iat")
        if iat is not None and iat > now + skew:
            raise OIDCAuthenticationError("OIDC ID token was issued in the future")
        _required_string(claims, "sub")

    def _jwk_for_kid(self, kid: str) -> dict[str, Any]:
        for key in self.jwks()["keys"]:
            if isinstance(key, dict) and key.get("kid") == kid:
                return key
        raise OIDCAuthenticationError("OIDC ID token key id was not found in JWKS")

    def _discovery_endpoint(self, key: str) -> str:
        return self._require_endpoint_url(_string_endpoint(self.discovery(), key))

    def _require_endpoint_url(self, url: str) -> str:
        return require_https_url(
            url,
            allow_loopback_http=self.config.oidc_allow_loopback_http,
            error_type=OIDCAuthenticationError,
        )

    def _get_json(self, url: str) -> dict[str, Any]:
        payload, _headers = self._get_json_with_headers(url)
        return payload

    def _get_json_with_headers(self, url: str) -> tuple[dict[str, Any], Mapping[str, str]]:
        http_request = request.Request(url, method="GET")
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                return _json_response(response.read()), response.headers
        except (TimeoutError, error.URLError) as exc:
            raise OIDCAuthenticationError("OIDC endpoint request failed") from exc

    def _post_form(
        self,
        url: str,
        payload: dict[str, str],
        *,
        allow_oauth_error: bool = False,
    ) -> dict[str, Any]:
        encoded_body = parse.urlencode(payload).encode("utf-8")
        http_request = request.Request(
            url,
            data=encoded_body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                return _json_response(response.read())
        except error.HTTPError as exc:
            error_payload = _json_response(exc.read())
            if allow_oauth_error and isinstance(error_payload.get("error"), str):
                return error_payload
            raise OIDCAuthenticationError("OIDC endpoint rejected the request") from exc
        except (TimeoutError, error.URLError) as exc:
            raise OIDCAuthenticationError("OIDC endpoint request failed") from exc


def _verify_signature(
    alg: str,
    jwk: dict[str, Any],
    signing_input: bytes,
    signature: bytes,
) -> None:
    kty = jwk.get("kty")
    if alg.startswith("HS") and kty != "oct":
        raise OIDCAuthenticationError("OIDC ID token algorithm is incompatible with JWKS key")
    if alg == "HS256":
        secret = _b64url_decode(_required_string(jwk, "k"))
        expected = hmac.new(secret, signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, signature):
            raise OIDCAuthenticationError("OIDC ID token signature was invalid")
        return
    if alg == "RS256" and kty == "RSA":
        _verify_rs256(jwk, signing_input, signature)
        return
    raise OIDCAuthenticationError("OIDC ID token uses an unsupported algorithm")


def _validate_authorization_state(expected_state: str, received_state: str | None) -> None:
    if not expected_state or not received_state:
        raise OIDCAuthenticationError("OIDC authorization state did not match")
    if not hmac.compare_digest(expected_state, received_state):
        raise OIDCAuthenticationError("OIDC authorization state did not match")


def _verify_rs256(jwk: dict[str, Any], signing_input: bytes, signature: bytes) -> None:
    n = int.from_bytes(_b64url_decode(_required_string(jwk, "n")), "big")
    e = int.from_bytes(_b64url_decode(_required_string(jwk, "e")), "big")
    key_bytes = (n.bit_length() + 7) // 8
    if len(signature) != key_bytes:
        raise OIDCAuthenticationError("OIDC ID token signature was invalid")
    decoded = pow(int.from_bytes(signature, "big"), e, n).to_bytes(key_bytes, "big")
    digest = hashlib.sha256(signing_input).digest()
    expected_suffix = RSA_SHA256_DIGEST_INFO + digest
    padding_length = key_bytes - len(expected_suffix) - 3
    if padding_length < 8:
        raise OIDCAuthenticationError("OIDC JWKS RSA key is too small")
    expected = b"\x00\x01" + (b"\xff" * padding_length) + b"\x00" + expected_suffix
    if not hmac.compare_digest(decoded, expected):
        raise OIDCAuthenticationError("OIDC ID token signature was invalid")


def _decode_jwt(token: str) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
    parts = token.split(".")
    if len(parts) != 3:
        raise OIDCAuthenticationError("OIDC ID token must have three JWT parts")
    header = _json_response(_b64url_decode(parts[0]))
    claims = _json_response(_b64url_decode(parts[1]))
    signature = _b64url_decode(parts[2])
    return header, claims, f"{parts[0]}.{parts[1]}".encode("ascii"), signature


def _json_response(value: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OIDCAuthenticationError("OIDC endpoint returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise OIDCAuthenticationError("OIDC endpoint JSON must be an object")
    return payload


def _string_endpoint(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise OIDCAuthenticationError(f"OIDC discovery metadata missing {key}")
    return value


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise OIDCAuthenticationError(f"OIDC token missing {key}")
    return value


def _optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def _timestamp_claim(payload: dict[str, Any], key: str) -> datetime:
    value = payload.get(key)
    if not isinstance(value, int | float):
        raise OIDCAuthenticationError(f"OIDC token missing {key}")
    return datetime.fromtimestamp(value, tz=UTC)


def _optional_timestamp_claim(payload: dict[str, Any], key: str) -> datetime | None:
    if key not in payload:
        return None
    return _timestamp_claim(payload, key)


def _groups_from_claim(value: Any) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, str) and value:
        return [value]
    return []


def _token_identifier(claims: dict[str, Any]) -> str:
    jti = claims.get("jti")
    if isinstance(jti, str) and jti:
        return jti
    seed = f"{claims.get('iss', '')}:{claims.get('sub', '')}:{claims.get('iat', '')}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _pkce_verifier() -> str:
    return secrets.token_urlsafe(48)


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padded = value + ("=" * ((4 - len(value) % 4) % 4))
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise OIDCAuthenticationError("OIDC token contained invalid base64url") from exc
