"""Tests for the ``craik-hook`` CLI gating client (``craik.runtime.hooks.client``).

The client half of the hook bridge, split out of ``hook_bridge`` so the
``craik-hook`` console entry imports only stdlib. Covers BOTH vendor decision
encodings (Anthropic ``permissionDecision`` and Google ``decision``) per
``docs/adapters/vendor-capabilities.md`` and
``docs/adapters/flows/{anthropic-cli,google-cli}.md``, the ``run_hook_client``
allow/deny round-trip against a real server, and the **fail-closed branches**:
unreachable socket, empty/whitespace stdin, a missing ``CRAIK_HOOK_SOCKET`` env
in ``craik_hook_main``, and an unknown vendor falling back to the conservative
Anthropic exit-2 deny. No real CLI binaries; a ``tmp_path`` socket and short
timeouts keep the suite fast.
"""

from __future__ import annotations

import io
import json
import threading
from pathlib import Path

from craik.runtime.backend.adapters.hook_bridge import HookBridgeServer
from craik.runtime.hooks.client import (
    craik_hook_main,
    encode_anthropic_decision,
    encode_google_decision,
    run_hook_client,
)


def _serve_once(server: HookBridgeServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_once, daemon=True)
    thread.start()
    return thread


# --- Vendor encoders --------------------------------------------------------


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


# --- run_hook_client round-trip against a live server -----------------------


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


# --- Fail-closed branches (Task 5.3 Item 2) ---------------------------------


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


def test_client_empty_stdin_denies_anthropic(tmp_path: Path) -> None:
    # Empty stdin is never forwarded: it is a vendor-correct fail-closed deny,
    # and the bridge is never even contacted (a server here would never accept).
    socket_path = tmp_path / "missing.sock"
    stdout = io.StringIO()
    code = run_hook_client(
        stdin=io.StringIO(""),
        stdout=stdout,
        socket_path=str(socket_path),
        vendor="anthropic",
        timeout=0.5,
    )
    assert json.loads(stdout.getvalue()) == {"hookSpecificOutput": {"permissionDecision": "deny"}}
    assert code == 2


def test_client_whitespace_only_stdin_denies_google(tmp_path: Path) -> None:
    socket_path = tmp_path / "missing.sock"
    stdout = io.StringIO()
    code = run_hook_client(
        stdin=io.StringIO("   \n\t  "),
        stdout=stdout,
        socket_path=str(socket_path),
        vendor="google",
        timeout=0.5,
    )
    assert json.loads(stdout.getvalue())["decision"] == "deny"
    assert code == 2


def test_main_missing_socket_env_denies_anthropic(monkeypatch, capsys) -> None:
    # ``craik_hook_main`` with no CRAIK_HOOK_SOCKET set -> no bridge configured,
    # so it must fail closed in the vendor-correct shape without forwarding.
    monkeypatch.delenv("CRAIK_HOOK_SOCKET", raising=False)
    monkeypatch.setenv("CRAIK_HOOK_VENDOR", "anthropic")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"tool_name": "Bash"})))

    code = craik_hook_main([])

    out = capsys.readouterr().out
    assert json.loads(out) == {"hookSpecificOutput": {"permissionDecision": "deny"}}
    assert code == 2


def test_main_missing_socket_env_denies_google(monkeypatch, capsys) -> None:
    monkeypatch.delenv("CRAIK_HOOK_SOCKET", raising=False)
    monkeypatch.setenv("CRAIK_HOOK_VENDOR", "google")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"name": "run_shell_command"})))

    code = craik_hook_main([])

    out = capsys.readouterr().out
    assert json.loads(out)["decision"] == "deny"
    assert code == 2


def test_main_unknown_vendor_falls_back_to_anthropic_exit2(monkeypatch, capsys) -> None:
    # An unknown CRAIK_HOOK_VENDOR is itself a fail-closed condition: the missing
    # socket path forces a deny, and the encoder defaults to the conservative
    # Anthropic exit-2 hard-block (the most conservative cross-vendor deny).
    monkeypatch.delenv("CRAIK_HOOK_SOCKET", raising=False)
    monkeypatch.setenv("CRAIK_HOOK_VENDOR", "totally-unknown-vendor")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"tool_name": "Bash"})))

    code = craik_hook_main([])

    out = capsys.readouterr().out
    assert json.loads(out) == {"hookSpecificOutput": {"permissionDecision": "deny"}}
    assert code == 2
