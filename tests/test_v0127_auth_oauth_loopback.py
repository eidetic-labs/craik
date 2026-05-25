from __future__ import annotations

import base64
import hashlib
import socket
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

import pytest

from craik.runtime.auth.oauth_loopback import (
    LOOPBACK_HOST,
    OAuthLoopbackError,
    OAuthLoopbackListener,
    authorization_url,
    generate_oauth_state,
    generate_pkce_challenge,
    validate_loopback_host,
)


def test_loopback_listener_binds_to_127001_and_random_port() -> None:
    listener = OAuthLoopbackListener(expected_state="state").start()
    try:
        assert listener.redirect_uri.startswith(f"http://{LOOPBACK_HOST}:")
        assert listener.port > 0
        assert listener.port != 80
    finally:
        listener.close()


def test_loopback_listener_accepts_one_valid_callback() -> None:
    listener = OAuthLoopbackListener(expected_state="expected-state").start()
    url = f"{listener.redirect_uri}?code=auth-code&state=expected-state"
    with urlopen(url, timeout=2) as response:
        assert response.status == 200

    result = listener.wait()

    assert result.code == "auth-code"
    assert result.state == "expected-state"
    assert result.params["code"] == "auth-code"


def test_loopback_listener_rejects_state_mismatch() -> None:
    listener = OAuthLoopbackListener(expected_state="expected-state").start()
    with pytest.raises(HTTPError):
        urlopen(f"{listener.redirect_uri}?code=auth-code&state=wrong-state", timeout=2)

    with pytest.raises(OAuthLoopbackError, match="state validation failed"):
        listener.wait()


def test_loopback_listener_times_out_and_closes() -> None:
    listener = OAuthLoopbackListener(expected_state="state", timeout_seconds=0.01).start()

    with pytest.raises(OAuthLoopbackError, match="timed out"):
        listener.wait()


def test_loopback_listener_rejects_invalid_callback_path() -> None:
    with pytest.raises(OAuthLoopbackError, match="must start with"):
        OAuthLoopbackListener(expected_state="state", callback_path="callback")


def test_loopback_host_is_not_publicly_bound() -> None:
    listener = OAuthLoopbackListener(expected_state="state").start()
    try:
        with socket.socket() as client:
            client.settimeout(2)
            client.connect((LOOPBACK_HOST, listener.port))
    finally:
        listener.close()


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "localhost", "192.168.1.10"])
def test_loopback_host_validator_rejects_non_literal_loopback_hosts(host: str) -> None:
    with pytest.raises(OAuthLoopbackError, match="127.0.0.1"):
        validate_loopback_host(host)


def test_oauth_state_generation_uses_high_entropy_urlsafe_value() -> None:
    first = generate_oauth_state()
    second = generate_oauth_state()

    assert first != second
    assert len(first) >= 32
    assert "\n" not in first


def test_pkce_challenge_uses_sha256_s256_without_padding() -> None:
    pkce = generate_pkce_challenge()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(pkce.verifier.encode("ascii")).digest()
    ).decode("ascii").rstrip("=")

    assert pkce.method == "S256"
    assert pkce.challenge == expected
    assert "=" not in pkce.challenge
    assert len(pkce.verifier) >= 64


def test_authorization_url_includes_state_pkce_and_scope() -> None:
    pkce = generate_pkce_challenge()

    url = authorization_url(
        "https://auth.example.test/oauth/authorize",
        client_id="client-id",
        redirect_uri="http://127.0.0.1:1234/oauth/callback",
        scope=["models.read", "responses.write"],
        state="state-value",
        pkce=pkce,
        extra_params={"audience": "provider-api"},
    )

    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert params["response_type"] == ["code"]
    assert params["client_id"] == ["client-id"]
    assert params["scope"] == ["models.read responses.write"]
    assert params["state"] == ["state-value"]
    assert params["code_challenge"] == [pkce.challenge]
    assert params["code_challenge_method"] == ["S256"]
    assert params["audience"] == ["provider-api"]
