from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from craik.runtime.providers.http_transport import HTTPTransport
from craik.runtime.providers.provider_runtime import (
    OPENAI_OFFICIAL_DOCS,
    ChatCompletionsProviderAdapter,
    ProviderMessage,
    ProviderRuntimeConfig,
    ProviderRuntimeRequest,
)
from craik.runtime.providers.provider_transport import ProviderTransport, ProviderTransportError


def test_http_transport_yields_non_streaming_json_response() -> None:
    seen: dict[str, Any] = {}

    def handle(payload: dict[str, Any], headers: dict[str, str]) -> _StubResponse:
        seen["payload"] = payload
        seen["authorization"] = headers.get("Authorization")
        return _json_response({"id": "resp_1", "output_text": "ok"})

    with _stub_server(handle) as server:
        transport = HTTPTransport(
            family="openai",
            base_url=server.url,
            headers_factory=lambda: {"Authorization": "Bearer craik-test-not-a-real-token"},
            timeout_seconds=5,
        )

        chunks = list(transport.send({"_path": "/v1/responses", "model": "gpt-test"}, stream=False))

    assert chunks == [{"id": "resp_1", "output_text": "ok"}]
    assert seen["payload"] == {"model": "gpt-test"}
    assert seen["authorization"] == "Bearer craik-test-not-a-real-token"


def test_provider_transport_protocol_defaults_raise_not_implemented() -> None:
    class IncompleteTransport(ProviderTransport):
        pass

    transport = IncompleteTransport()

    def read_family() -> object:
        return transport.family

    with pytest.raises(NotImplementedError):
        read_family()
    with pytest.raises(NotImplementedError):
        list(transport.send({}, stream=False))


def test_http_transport_yields_sse_json_chunks() -> None:
    def handle(payload: dict[str, Any], headers: dict[str, str]) -> _StubResponse:
        return _sse_response(
            [
                'event: message\n',
                'data: {"delta":"Hel"}\n\n',
                ': keep-alive\n',
                'data: {"delta":"lo"}\n\n',
                'data: [DONE]\n\n',
            ]
        )

    with _stub_server(handle) as server:
        transport = HTTPTransport(
            family="anthropic",
            base_url=server.url,
            headers_factory=dict,
            timeout_seconds=5,
        )

        chunks = list(transport.send({"_path": "/v1/messages", "stream": True}, stream=True))

    assert chunks == [{"delta": "Hel"}, {"delta": "lo"}]


def test_http_transport_stream_stops_when_cancelled_between_chunks() -> None:
    cancel_event = threading.Event()

    def handle(payload: dict[str, Any], headers: dict[str, str]) -> _StubResponse:
        return _sse_response(
            [
                'data: {"delta":"Hel"}\n\n',
                'data: {"delta":"lo"}\n\n',
                'data: [DONE]\n\n',
            ]
        )

    with _stub_server(handle) as server:
        transport = HTTPTransport(
            family="chat_completions",
            base_url=server.url,
            headers_factory=dict,
            timeout_seconds=5,
            cancel_event=cancel_event,
        )

        iterator = transport.send({"_path": "/v1/chat/completions"}, stream=True)
        assert next(iterator) == {"delta": "Hel"}
        cancel_event.set()
        with pytest.raises(ProviderTransportError, match="cancelled"):
            next(iterator)


def test_http_transport_error_redacts_body_and_preserves_retry_after() -> None:
    def handle(payload: dict[str, Any], headers: dict[str, str]) -> _StubResponse:
        return _json_response(
            {"error": "token=craik-test-not-a-real-key-01 failed"},
            status=429,
            headers={"Retry-After": "3"},
        )

    with _stub_server(handle) as server:
        transport = HTTPTransport(
            family="openai",
            base_url=server.url,
            headers_factory=lambda: {"Authorization": "Bearer secret-auth-token"},
            timeout_seconds=5,
        )

        try:
            list(transport.send({"_path": "/v1/responses"}, stream=False))
        except ProviderTransportError as exc:
            error = exc
        else:  # pragma: no cover - defensive assertion path
            raise AssertionError("expected ProviderTransportError")

    assert error.status_code == 429
    assert error.retry_after_seconds == 3
    assert "craik-test-not-a-real-key-01" not in str(error)
    assert "secret-auth-token" not in str(error)
    assert error.body is not None
    assert "craik-test-not-a-real-key-01" not in error.body
    assert error.headers["content-type"] == "application/json"
    assert error.headers["retry-after"] == "3"
    assert "server" not in error.headers


def test_http_transport_error_drops_sensitive_headers_and_redacts_safe_values() -> None:
    def handle(payload: dict[str, Any], headers: dict[str, str]) -> _StubResponse:
        return _json_response(
            {"error": "token=craik-test-not-a-real-key-body"},
            status=401,
            headers={
                "WWW-Authenticate": 'Bearer realm="api", error="invalid_token"',
                "X-API-Key": "craik-test-not-a-real-key-header",
                "X-Request-Id": "token=craik-test-not-a-real-key-request",
                "Retry-After": "30",
            },
        )

    with _stub_server(handle) as server:
        transport = HTTPTransport(
            family="openai",
            base_url=server.url,
            headers_factory=dict,
            timeout_seconds=5,
        )

        with pytest.raises(ProviderTransportError) as exc_info:
            list(transport.send({"_path": "/v1/responses"}, stream=False))

    error = exc_info.value
    assert error.retry_after_seconds == 30
    assert "www-authenticate" not in error.headers
    assert "x-api-key" not in error.headers
    assert error.headers["retry-after"] == "30"
    assert error.headers["x-request-id"] == "token=[REDACTED]"
    assert error.body is not None
    assert "craik-test-not-a-real-key-body" not in error.body
    assert "craik-test-not-a-real-key-header" not in str(error)


def test_http_transport_builds_headers_for_each_request() -> None:
    seen_authorizations: list[str | None] = []
    token = {"value": "first-token"}

    def handle(payload: dict[str, Any], headers: dict[str, str]) -> _StubResponse:
        seen_authorizations.append(headers.get("Authorization"))
        return _json_response({"id": "resp", "output_text": "ok"})

    with _stub_server(handle) as server:
        transport = HTTPTransport(
            family="openai",
            base_url=server.url,
            headers_factory=lambda: {"Authorization": f"Bearer {token['value']}"},
            timeout_seconds=5,
        )

        list(transport.send({"_path": "/v1/responses"}, stream=False))
        token["value"] = "second-token"
        list(transport.send({"_path": "/v1/responses"}, stream=False))

    assert seen_authorizations == ["Bearer first-token", "Bearer second-token"]


def test_http_transport_does_not_duplicate_v1_prefix_for_openai_compatible_base_url() -> None:
    seen: dict[str, Any] = {}

    def handle(payload: dict[str, Any], headers: dict[str, str]) -> _StubResponse:
        seen["path"] = headers["X-Request-Path"]
        return _json_response({"id": "chatcmpl_1", "choices": []})

    with _stub_server(handle) as server:
        transport = HTTPTransport(
            family="chat_completions",
            base_url=f"{server.url}/v1",
            headers_factory=dict,
            timeout_seconds=5,
        )

        list(transport.send({"_path": "/v1/chat/completions"}, stream=False))

    assert seen["path"] == "/v1/chat/completions"


def test_live_enabled_adapter_executes_round_trip_through_http_transport() -> None:
    seen: dict[str, Any] = {}

    def handle(payload: dict[str, Any], headers: dict[str, str]) -> _StubResponse:
        seen["payload"] = payload
        return _json_response(
            {
                "id": "chatcmpl_live_stub",
                "model": payload["model"],
                "choices": [{"message": {"role": "assistant", "content": "live stub ok"}}],
                "usage": {
                    "prompt_tokens": 4,
                    "completion_tokens": 3,
                    "total_tokens": 7,
                },
            }
        )

    with _stub_server(handle) as server:
        config = ProviderRuntimeConfig(
            provider_id="provider_openai_chat_stub",
            provider_family="chat_completions",
            model="gpt-test",
            secret_ref_name="TEST_API_KEY",
            base_url=server.url,
            allow_local_base_url=True,
            live_enabled=True,
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
        )
        adapter = ChatCompletionsProviderAdapter(
            config,
            transport=HTTPTransport(
                family="chat_completions",
                base_url=server.url,
                headers_factory=dict,
                timeout_seconds=5,
            ),
        )

        result = adapter.execute(
            ProviderRuntimeRequest(
                messages=[ProviderMessage(role="user", content="Say ok.")],
            )
        )

    assert seen["payload"] == {
        "model": "gpt-test",
        "messages": [{"role": "user", "content": "Say ok."}],
        "stream": False,
        "max_tokens": 1024,
    }
    assert result.text == "live stub ok"
    assert result.response_id == "chatcmpl_live_stub"
    assert result.usage == {"input_tokens": 4, "output_tokens": 3, "total_tokens": 7}


def test_live_enabled_adapter_retries_retryable_http_errors() -> None:
    seen = {"requests": 0}

    def handle(payload: dict[str, Any], headers: dict[str, str]) -> _StubResponse:
        seen["requests"] += 1
        if seen["requests"] < 3:
            return _json_response(
                {"error": "rate limited"},
                status=429,
                headers={"Retry-After": "0"},
            )
        return _json_response(
            {
                "id": "chatcmpl_retry_stub",
                "model": payload["model"],
                "choices": [{"message": {"role": "assistant", "content": "retry ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            }
        )

    with _stub_server(handle) as server:
        config = ProviderRuntimeConfig(
            provider_id="provider_openai_chat_retry_stub",
            provider_family="chat_completions",
            model="gpt-test",
            secret_ref_name="TEST_API_KEY",
            base_url=server.url,
            allow_local_base_url=True,
            live_enabled=True,
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
        )
        adapter = ChatCompletionsProviderAdapter(
            config,
            transport=HTTPTransport(
                family="chat_completions",
                base_url=server.url,
                headers_factory=dict,
                timeout_seconds=5,
            ),
        )

        result = adapter.execute(
            ProviderRuntimeRequest(
                messages=[ProviderMessage(role="user", content="Say ok.")],
            )
        )

    assert seen["requests"] == 3
    assert result.text == "retry ok"


def test_live_enabled_adapter_does_not_retry_429_without_retry_after() -> None:
    seen = {"requests": 0}

    def handle(payload: dict[str, Any], headers: dict[str, str]) -> _StubResponse:
        seen["requests"] += 1
        return _json_response({"error": "rate limited"}, status=429)

    with _stub_server(handle) as server:
        config = ProviderRuntimeConfig(
            provider_id="provider_openai_chat_rate_limit_stub",
            provider_family="chat_completions",
            model="gpt-test",
            secret_ref_name="TEST_API_KEY",
            base_url=server.url,
            allow_local_base_url=True,
            live_enabled=True,
            docs_refs=list(OPENAI_OFFICIAL_DOCS),
        )
        adapter = ChatCompletionsProviderAdapter(
            config,
            transport=HTTPTransport(
                family="chat_completions",
                base_url=server.url,
                headers_factory=dict,
                timeout_seconds=5,
            ),
        )

        with pytest.raises(ProviderTransportError):
            adapter.execute(
                ProviderRuntimeRequest(
                    messages=[ProviderMessage(role="user", content="Say ok.")],
                )
            )

    assert seen["requests"] == 1


class _StubResponse:
    def __init__(
        self,
        *,
        body: bytes,
        status: int = 200,
        headers: dict[str, str] | None = None,
        content_type: str = "application/json",
    ) -> None:
        self.body = body
        self.status = status
        self.headers = {"Content-Type": content_type, **(headers or {})}


def _json_response(
    payload: dict[str, Any],
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> _StubResponse:
    return _StubResponse(body=json.dumps(payload).encode("utf-8"), status=status, headers=headers)


def _sse_response(lines: list[str]) -> _StubResponse:
    return _StubResponse(
        body="".join(lines).encode("utf-8"),
        content_type="text/event-stream",
    )


class _Node:
    def __init__(self, server: HTTPServer, thread: threading.Thread) -> None:
        self._server = server
        self._thread = thread
        self.url = f"http://127.0.0.1:{server.server_port}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def __enter__(self) -> _Node:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _stub_server(handler: Any) -> _Node:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
            headers = dict(self.headers.items())
            headers["X-Request-Path"] = self.path
            response = handler(payload, headers)
            self.send_response(response.status)
            for key, value in response.headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(response.body)))
            self.end_headers()
            self.wfile.write(response.body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return _Node(server, thread)
