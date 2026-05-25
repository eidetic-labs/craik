import json
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from pydantic import ValidationError

from craik.runtime.auth import AuthProfile, CredentialKind, CredentialSource, CredentialStatus
from craik.runtime.auth.sources import (
    CLIBridgeCredentialSource,
    EnvVarApiKeySource,
    SecretRefCredentialSource,
    StigmemCredentialError,
    StigmemCredentialSource,
    source_for_auth_profile,
)


def test_auth_profile_round_trips_through_json() -> None:
    profile = AuthProfile(
        id="anthropic:work",
        kind=CredentialKind.API_KEY,
        provider_family="anthropic",
        metadata={"env_var": "ANTHROPIC_API_KEY"},
        created_at=datetime(2026, 5, 17, tzinfo=UTC),
        last_status="ok",
        redaction_patterns=[r"work-account@example\.test"],
    )

    restored = AuthProfile.model_validate_json(profile.model_dump_json())

    assert restored == profile
    assert restored.kind is CredentialKind.API_KEY
    assert restored.metadata["env_var"] == "ANTHROPIC_API_KEY"
    assert restored.redaction_patterns == [r"work-account@example\.test"]


def test_oauth_auth_profile_requires_complete_oauth_metadata() -> None:
    with pytest.raises(ValidationError, match="oauth auth profiles require"):
        AuthProfile(
            id="openai:subscription",
            kind=CredentialKind.OAUTH,
            provider_family="openai",
            created_at=datetime(2026, 5, 24, tzinfo=UTC),
            oauth_authorization_endpoint="https://auth.openai.example/authorize",
        )


def test_oauth_auth_profile_round_trips_through_json() -> None:
    profile = AuthProfile(
        id="openai:subscription",
        kind=CredentialKind.OAUTH,
        provider_family="openai",
        created_at=datetime(2026, 5, 24, tzinfo=UTC),
        oauth_authorization_endpoint="https://auth.openai.example/authorize",
        oauth_token_endpoint="https://auth.openai.example/token",
        oauth_client_id="craik-public-client",
        oauth_scope_list=["models.read", "responses.write"],
        oauth_token_keyring_handle="craik:openai:subscription:access",
        oauth_refresh_keyring_handle="craik:openai:subscription:refresh",
        oauth_last_refreshed_at=datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
    )

    restored = AuthProfile.model_validate_json(profile.model_dump_json())

    assert restored == profile
    assert restored.kind is CredentialKind.OAUTH
    assert restored.oauth_scope_list == ["models.read", "responses.write"]
    assert restored.oauth_token_keyring_handle == "craik:openai:subscription:access"
    assert restored.oauth_refresh_keyring_handle == "craik:openai:subscription:refresh"


def test_legacy_local_cli_oauth_token_profiles_do_not_require_provider_oauth_fields() -> None:
    profile = AuthProfile(
        id="openai:local-cli",
        kind=CredentialKind.OAUTH_TOKEN,
        provider_family="openai",
        metadata={"source": "local-cli"},
        created_at=datetime(2026, 5, 24, tzinfo=UTC),
    )

    assert profile.oauth_authorization_endpoint is None
    assert profile.oauth_refresh_keyring_handle is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("oauth_authorization_endpoint", ""),
        ("oauth_token_endpoint", " "),
        ("oauth_client_id", "\t"),
        ("oauth_scope_list", []),
        ("oauth_scope_list", ["models.read", ""]),
        ("oauth_token_keyring_handle", "\n"),
        ("oauth_refresh_keyring_handle", ""),
    ],
)
def test_oauth_auth_profile_rejects_blank_oauth_metadata(field: str, value: object) -> None:
    kwargs: dict[str, object] = {
        "oauth_authorization_endpoint": "https://auth.openai.example/authorize",
        "oauth_token_endpoint": "https://auth.openai.example/token",
        "oauth_client_id": "craik-public-client",
        "oauth_scope_list": ["models.read"],
        "oauth_token_keyring_handle": "craik:openai:subscription:access",
        "oauth_refresh_keyring_handle": "craik:openai:subscription:refresh",
    }
    kwargs[field] = value

    with pytest.raises(ValidationError, match="oauth"):
        AuthProfile(
            id="openai:subscription",
            kind=CredentialKind.OAUTH,
            provider_family="openai",
            created_at=datetime(2026, 5, 24, tzinfo=UTC),
            **kwargs,
        )


def test_auth_profile_rejects_id_without_profile_name() -> None:
    with pytest.raises(ValidationError, match="<provider_family>:<name>"):
        AuthProfile(
            id="anthropic",
            kind=CredentialKind.API_KEY,
            provider_family="anthropic",
            created_at=datetime(2026, 5, 17, tzinfo=UTC),
        )


def test_auth_profile_rejects_mismatched_provider_family() -> None:
    with pytest.raises(ValidationError, match="provider family must match"):
        AuthProfile(
            id="openai:work",
            kind=CredentialKind.OAUTH_TOKEN,
            provider_family="anthropic",
            created_at=datetime(2026, 5, 17, tzinfo=UTC),
        )


def test_auth_profile_rejects_invalid_redaction_pattern() -> None:
    with pytest.raises(ValidationError, match="redaction pattern is invalid"):
        AuthProfile(
            id="openai:work",
            kind=CredentialKind.API_KEY,
            provider_family="openai",
            redaction_patterns=["["],
            created_at=datetime(2026, 5, 17, tzinfo=UTC),
        )


def test_credential_status_defaults_to_unknown() -> None:
    status = CredentialStatus()

    assert status.status == "unknown"
    assert status.detail is None
    assert status.expires_at is None


def test_credential_source_protocol_defaults_raise_not_implemented() -> None:
    class IncompleteCredentialSource(CredentialSource):
        pass

    source = IncompleteCredentialSource()

    with pytest.raises(NotImplementedError):
        source.headers_for("openai")
    with pytest.raises(NotImplementedError):
        source.status()


def test_source_for_auth_profile_maps_supported_kinds() -> None:
    created_at = datetime(2026, 5, 17, tzinfo=UTC)

    api_key = source_for_auth_profile(
        AuthProfile(
            id="anthropic:work",
            kind=CredentialKind.API_KEY,
            provider_family="anthropic",
            metadata={"env_var": "ANTHROPIC_API_KEY"},
            created_at=created_at,
        )
    )
    secret_ref = source_for_auth_profile(
        AuthProfile(
            id="openai:secret",
            kind=CredentialKind.SECRET_REF,
            provider_family="openai",
            metadata={"manager": "env", "ref": "OPENAI_API_KEY"},
            created_at=created_at,
        )
    )
    cli_bridge = source_for_auth_profile(
        AuthProfile(
            id="chat_completions:bridge",
            kind=CredentialKind.CLI_BRIDGE,
            provider_family="chat_completions",
            metadata={"command": ["echo", '{"token":"craik-test-not-a-real-key"}']},
            created_at=created_at,
        )
    )
    stigmem_ref = source_for_auth_profile(
        AuthProfile(
            id="openai:stigmem",
            kind=CredentialKind.STIGMEM_REF,
            provider_family="openai",
            metadata={
                "node_url": "http://127.0.0.1:1",
                "entity": "credential:openai:work",
            },
            created_at=created_at,
        )
    )

    assert isinstance(api_key, EnvVarApiKeySource)
    assert isinstance(secret_ref, SecretRefCredentialSource)
    assert isinstance(cli_bridge, CLIBridgeCredentialSource)
    assert isinstance(stigmem_ref, StigmemCredentialSource)


def test_stigmem_credential_source_resolves_fact_value() -> None:
    server, thread = _stigmem_credential_server("craik-test-not-a-real-stigmem-key")
    try:
        source = StigmemCredentialSource.from_config(
            node_url=_server_url(server),
            api_key="test-key",
            entity="credential:openai:work",
        )

        assert source.headers_for("openai") == {
            "Authorization": "Bearer craik-test-not-a-real-stigmem-key"
        }
        assert source.status().status == "ok"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_stigmem_credential_source_returns_gemini_header() -> None:
    server, thread = _stigmem_credential_server("craik-test-not-a-real-stigmem-key")
    try:
        source = StigmemCredentialSource.from_config(
            node_url=_server_url(server),
            api_key="test-key",
            entity="credential:gemini:work",
        )

        assert source.headers_for("gemini") == {
            "x-goog-api-key": "craik-test-not-a-real-stigmem-key"
        }
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_stigmem_credential_source_fails_when_fact_is_revoked() -> None:
    server, thread = _stigmem_credential_server(None)
    try:
        source = StigmemCredentialSource.from_config(
            node_url=_server_url(server),
            api_key="test-key",
            entity="credential:openai:work",
        )

        with pytest.raises(StigmemCredentialError, match="could not resolve"):
            source.headers_for("openai")
        assert source.status().status == "rejected"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _stigmem_credential_server(secret: str | None) -> tuple[HTTPServer, threading.Thread]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path.startswith("/v1/facts"):
                if self.headers.get("Authorization") != "Bearer test-key":
                    self._json({"error": "unauthorized"}, status=401)
                    return
                facts: list[dict[str, Any]] = []
                if secret is not None:
                    facts.append(
                        {
                            "entity": "credential:openai:work",
                            "relation": "craik:credential:value",
                            "value": {"type": "text", "v": secret},
                            "source": "stigmem:test",
                            "confidence": 1.0,
                            "scope": "team",
                            "trust_class": "policy",
                        }
                    )
                self._json({"facts": facts})
                return
            self._json({"error": "not found"}, status=404)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _json(self, payload: dict[str, Any], *, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _server_url(server: HTTPServer) -> str:
    return f"http://127.0.0.1:{server.server_port}"
