"""Tests for the gateway-side hook-bridge daemon RPC server (Phase 5 Task 5.1).

Covers the :class:`HookBridgeServer` round-trip for allow + deny, the
safe-default deny on a malformed payload, the throwing-``decide`` survival of
the accept loop, and the socket-file lifecycle. The CLIENT half (encoders,
``forward_tool_request``, ``run_hook_client``, ``craik_hook_main``) now lives in
``craik.runtime.hooks.client`` and is tested in ``tests/runtime/hooks``; this
file imports ``forward_tool_request`` from there to drive the server. No real
CLI binaries; a ``tmp_path`` socket and short timeouts keep the suite fast.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from craik.runtime.backend.adapters.hook_bridge import HookBridgeServer
from craik.runtime.hooks.client import forward_tool_request


def _serve_once(server: HookBridgeServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_once, daemon=True)
    thread.start()
    return thread


def test_server_round_trips_allow(tmp_path: Path) -> None:
    socket_path = tmp_path / "bridge.sock"
    with HookBridgeServer(str(socket_path), decide=lambda payload: "allow") as server:
        thread = _serve_once(server)
        decision = forward_tool_request(
            str(socket_path), {"tool_name": "Bash", "command": "echo hi"}, timeout=2.0
        )
        thread.join(timeout=2.0)
    assert decision == "allow"


def test_server_round_trips_deny(tmp_path: Path) -> None:
    socket_path = tmp_path / "bridge.sock"
    with HookBridgeServer(str(socket_path), decide=lambda payload: "deny") as server:
        thread = _serve_once(server)
        decision = forward_tool_request(
            str(socket_path), {"tool_name": "Bash", "command": "rm -rf /"}, timeout=2.0
        )
        thread.join(timeout=2.0)
    assert decision == "deny"


def test_server_malformed_payload_denies(tmp_path: Path) -> None:
    socket_path = tmp_path / "bridge.sock"
    seen: list[dict[str, Any]] = []

    def decide(payload: dict[str, Any]) -> str:
        seen.append(payload)
        return "allow"

    with HookBridgeServer(str(socket_path), decide=decide) as server:
        thread = _serve_once(server)
        import socket as _socket

        client = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        client.settimeout(2.0)
        client.connect(str(socket_path))
        client.sendall(b"this is not json\n")
        response = client.recv(4096).decode("utf-8")
        client.close()
        thread.join(timeout=2.0)
    # Malformed payload is a safe-default deny and ``decide`` is never consulted.
    assert json.loads(response.strip())["decision"] == "deny"
    assert seen == []


def test_throwing_decide_denies_and_loop_survives(tmp_path: Path) -> None:
    # A ``decide`` that RAISES on its first call must NOT tear down the accept
    # loop: the current request fails closed (deny reply written to THIS client)
    # and a second forwarded request still reaches ``decide`` and round-trips.
    socket_path = tmp_path / "bridge.sock"
    calls: list[dict[str, Any]] = []

    def decide(payload: dict[str, Any]) -> str:
        calls.append(payload)
        if len(calls) == 1:
            raise RuntimeError("boom on first call")
        return "allow"

    with HookBridgeServer(str(socket_path), decide=decide) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        # First request: ``decide`` raises -> per-request deny, loop survives.
        first = forward_tool_request(str(socket_path), {"tool_name": "Bash", "req": 1}, timeout=2.0)
        # Second request: proves the accept loop did NOT die from the exception.
        second = forward_tool_request(
            str(socket_path), {"tool_name": "Bash", "req": 2}, timeout=2.0
        )
        server.close()
        thread.join(timeout=2.0)

    assert first == "deny"
    assert second == "allow"
    # ``decide`` was called twice -> the accept loop reached a SECOND connection.
    assert len(calls) == 2


def test_lifecycle_creates_and_removes_socket(tmp_path: Path) -> None:
    socket_path = tmp_path / "bridge.sock"
    server = HookBridgeServer(str(socket_path), decide=lambda payload: "allow")
    server.start()
    assert socket_path.exists()
    server.close()
    assert not socket_path.exists()
