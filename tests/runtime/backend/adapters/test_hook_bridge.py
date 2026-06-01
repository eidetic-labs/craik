"""Tests for the hook-bridge daemon RPC + ``craik-hook`` client (Phase 5 Task 5.1).

Covers BOTH vendor decision encodings (Anthropic ``permissionDecision`` and
Google ``decision``) per ``docs/adapters/vendor-capabilities.md`` and
``docs/adapters/flows/{anthropic-cli,google-cli}.md``, the server round-trip for
allow + deny, the fail-closed deny on an unreachable socket, and the socket-file
lifecycle. No real CLI binaries; a ``tmp_path`` socket and short timeouts keep
the suite fast.
"""

from __future__ import annotations

import io
import json
import threading
from pathlib import Path
from typing import Any

from craik.runtime.backend.adapters.hook_bridge import (
    HookBridgeServer,
    encode_anthropic_decision,
    encode_google_decision,
    forward_tool_request,
    run_hook_client,
)


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


def test_encode_anthropic_allow() -> None:
    stdout_json, exit_code = encode_anthropic_decision("allow")
    assert json.loads(stdout_json) == {"hookSpecificOutput": {"permissionDecision": "allow"}}
    assert exit_code == 0


def test_encode_anthropic_deny_uses_exit_2() -> None:
    stdout_json, exit_code = encode_anthropic_decision("deny")
    assert json.loads(stdout_json) == {"hookSpecificOutput": {"permissionDecision": "deny"}}
    # Exit-2 is the reliable hard-block per vendor-capabilities.md line 46.
    assert exit_code == 2


def test_encode_google_allow_is_no_decision() -> None:
    stdout_json, exit_code = encode_google_decision("allow")
    # Allow = no decision / exit 0 per vendor-capabilities.md line 26.
    assert json.loads(stdout_json) == {}
    assert exit_code == 0


def test_encode_google_deny() -> None:
    stdout_json, exit_code = encode_google_decision("deny")
    payload = json.loads(stdout_json)
    assert payload["decision"] == "deny"
    assert "reason" in payload
    assert exit_code == 2


def test_client_encodes_allow_anthropic(tmp_path: Path) -> None:
    socket_path = tmp_path / "bridge.sock"
    stdin = io.StringIO(json.dumps({"tool_name": "Bash"}))
    stdout = io.StringIO()
    with HookBridgeServer(str(socket_path), decide=lambda payload: "allow") as server:
        thread = _serve_once(server)
        code = run_hook_client(
            stdin=stdin,
            stdout=stdout,
            socket_path=str(socket_path),
            vendor="anthropic",
            timeout=2.0,
        )
        thread.join(timeout=2.0)
    assert json.loads(stdout.getvalue()) == {"hookSpecificOutput": {"permissionDecision": "allow"}}
    assert code == 0


def test_client_encodes_deny_anthropic(tmp_path: Path) -> None:
    socket_path = tmp_path / "bridge.sock"
    stdin = io.StringIO(json.dumps({"tool_name": "Bash"}))
    stdout = io.StringIO()
    with HookBridgeServer(str(socket_path), decide=lambda payload: "deny") as server:
        thread = _serve_once(server)
        code = run_hook_client(
            stdin=stdin,
            stdout=stdout,
            socket_path=str(socket_path),
            vendor="anthropic",
            timeout=2.0,
        )
        thread.join(timeout=2.0)
    assert json.loads(stdout.getvalue()) == {"hookSpecificOutput": {"permissionDecision": "deny"}}
    assert code == 2


def test_client_encodes_allow_google(tmp_path: Path) -> None:
    socket_path = tmp_path / "bridge.sock"
    stdin = io.StringIO(json.dumps({"name": "run_shell_command"}))
    stdout = io.StringIO()
    with HookBridgeServer(str(socket_path), decide=lambda payload: "allow") as server:
        thread = _serve_once(server)
        code = run_hook_client(
            stdin=stdin,
            stdout=stdout,
            socket_path=str(socket_path),
            vendor="google",
            timeout=2.0,
        )
        thread.join(timeout=2.0)
    assert json.loads(stdout.getvalue()) == {}
    assert code == 0


def test_client_encodes_deny_google(tmp_path: Path) -> None:
    socket_path = tmp_path / "bridge.sock"
    stdin = io.StringIO(json.dumps({"name": "run_shell_command"}))
    stdout = io.StringIO()
    with HookBridgeServer(str(socket_path), decide=lambda payload: "deny") as server:
        thread = _serve_once(server)
        code = run_hook_client(
            stdin=stdin,
            stdout=stdout,
            socket_path=str(socket_path),
            vendor="google",
            timeout=2.0,
        )
        thread.join(timeout=2.0)
    payload = json.loads(stdout.getvalue())
    assert payload["decision"] == "deny"
    assert code == 2


def test_client_fail_closed_on_unreachable_socket(tmp_path: Path) -> None:
    # No server is listening at this path -> the connect fails.
    socket_path = tmp_path / "missing.sock"
    stdin = io.StringIO(json.dumps({"tool_name": "Bash"}))
    stdout = io.StringIO()
    code = run_hook_client(
        stdin=stdin,
        stdout=stdout,
        socket_path=str(socket_path),
        vendor="anthropic",
        timeout=0.5,
    )
    # Fail-closed: an unreachable bridge emits a vendor-correct DENY, never allow.
    assert json.loads(stdout.getvalue()) == {"hookSpecificOutput": {"permissionDecision": "deny"}}
    assert code == 2


def test_client_fail_closed_google_on_unreachable_socket(tmp_path: Path) -> None:
    socket_path = tmp_path / "missing.sock"
    stdin = io.StringIO(json.dumps({"name": "run_shell_command"}))
    stdout = io.StringIO()
    code = run_hook_client(
        stdin=stdin,
        stdout=stdout,
        socket_path=str(socket_path),
        vendor="google",
        timeout=0.5,
    )
    assert json.loads(stdout.getvalue())["decision"] == "deny"
    assert code == 2
