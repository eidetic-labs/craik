"""The ``craik-hook`` CLI pre-tool gating client (thin, stdlib-only).

This is the client half of the hook bridge, split out of
:mod:`craik.runtime.backend.adapters.hook_bridge` so the ``craik-hook`` console
script's import chain stays tiny. The hook fires on EVERY CLI tool call once
live, so this module imports ONLY stdlib (``json`` / ``os`` / ``socket`` /
``sys``) -- never ``backend.events``, the adapter registry, or any concrete
adapter. The gateway-side :class:`HookBridgeServer` stays in ``hook_bridge``.

:func:`run_hook_client` (entrypoint :func:`craik_hook_main`) reads the CLI's
tool-request JSON from stdin, connects to the bridge Unix socket, forwards the
payload, blocks for the **vendor-agnostic transport decision** (JSON
``{"decision": ...}``), then **encodes it in the VENDOR-CORRECT shape** on
stdout and returns the documented exit code. The vendor encoders live HERE (not
on the concrete adapters or the server) because only the client encodes
vendor-correctly, and a concrete adapter that needs an encoder imports it from
this module.

Protocols (source of truth: ``docs/adapters/vendor-capabilities.md`` line 26 and
``docs/adapters/flows/{anthropic-cli,google-cli}.md``):

- **Anthropic** (and the matching Codex permission JSON): allow -> JSON
  ``{"hookSpecificOutput": {"permissionDecision": "allow"}}`` exit 0; deny ->
  the same JSON with ``"deny"`` **plus exit code 2** (exit-2 is the reliable
  hard-block; ``permissionDecision: "deny"`` JSON alone is subject to native
  settings precedence -- vendor-capabilities.md line 46, anthropic-cli.md §3.4).
- **Google** (Gemini ``BeforeTool``): allow -> no decision / exit 0 (emit
  ``{}``); deny -> JSON ``{"decision": "deny", "reason": ...}`` plus exit code 2
  (vendor-capabilities.md line 26/93, google-cli.md §3.4).

**Open-risk note (fail-closed):** a timeout, dropped connection, unreachable
socket, malformed decision, empty/unreadable stdin, a missing socket env, or an
unknown vendor are all resolved as **deny** -- never a silent allow.
"""

from __future__ import annotations

import json
import os
import socket
import sys
from collections.abc import Callable
from typing import Any, TextIO

# Shared socket wire-framing (stdlib-only, so importing it keeps this thin
# client free of ``backend.events`` / ``backend.adapters``). Single source of
# truth for both bridge halves; see ``_transport`` module docstring.
from craik.runtime.hooks._transport import (
    _decode_payload,
    _read_message,
    _write_message,
)

# Decision vocabulary on the transport (vendor-agnostic). Canonical definition:
# the gateway-side ``hook_bridge`` module imports these from here so the client
# never pulls in the server module (and the server's import cost is irrelevant).
_ALLOW = "allow"
_DENY = "deny"

# The CLI pre-tool hook's documented blocking timeout is 600 s
# (vendor-capabilities.md line 47). The client default is well under that so a
# stuck bridge fails closed long before the CLI's own timeout fires.
_MAX_HOOK_TIMEOUT_SECONDS = 600.0
_DEFAULT_CLIENT_TIMEOUT_SECONDS = 30.0

# Env vars the gateway sets when it spawns the CLI so the hook script can find
# the bridge and know which vendor dialect to emit. Canonical here; re-exported
# from ``hook_bridge`` for the gateway-side adapters that register the hook.
SOCKET_ENV = "CRAIK_HOOK_SOCKET"
VENDOR_ENV = "CRAIK_HOOK_VENDOR"

# Default deny rationale surfaced to the CLI/operator on a fail-closed decision.
_DENY_REASON = "craik withheld authorization for this tool call"


def forward_tool_request(
    socket_path: str,
    payload: dict[str, Any],
    *,
    timeout: float = _DEFAULT_CLIENT_TIMEOUT_SECONDS,
) -> str:
    """Forward ``payload`` to the bridge and return the transport decision.

    Fail-closed: any connection error, timeout, or malformed reply yields
    ``"deny"`` rather than raising.
    """
    bounded = min(max(timeout, 0.0), _MAX_HOOK_TIMEOUT_SECONDS)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(bounded)
            client.connect(socket_path)
            _write_message(client, payload)
            reply = _read_message(client)
    except OSError:
        return _DENY
    if not isinstance(reply, dict):
        return _DENY
    return _ALLOW if reply.get("decision") == _ALLOW else _DENY


def encode_anthropic_decision(decision: str) -> tuple[str, int]:
    """Encode an allow/deny in the Anthropic (and Codex) hook shape.

    Returns ``(stdout_json, exit_code)``. allow -> ``permissionDecision: allow``
    exit 0; deny -> ``permissionDecision: deny`` **plus exit code 2** (the
    reliable hard-block per vendor-capabilities.md line 46).
    """
    verdict = _ALLOW if decision == _ALLOW else _DENY
    body = {"hookSpecificOutput": {"permissionDecision": verdict}}
    exit_code = 0 if verdict == _ALLOW else 2
    return json.dumps(body), exit_code


def encode_google_decision(decision: str) -> tuple[str, int]:
    """Encode an allow/deny in the Gemini ``BeforeTool`` hook shape.

    Returns ``(stdout_json, exit_code)``. allow -> no decision / exit 0 (emit an
    empty object, per vendor-capabilities.md line 26); deny -> ``decision: deny``
    with a ``reason`` **plus exit code 2** (line 93, the reliable hard-block).
    """
    if decision == _ALLOW:
        return json.dumps({}), 0
    body = {"decision": _DENY, "reason": _DENY_REASON}
    return json.dumps(body), 2


_ENCODERS: dict[str, Callable[[str], tuple[str, int]]] = {
    "anthropic": encode_anthropic_decision,
    "google": encode_google_decision,
}


def _encoder_for(vendor: str) -> Callable[[str], tuple[str, int]]:
    # An unknown vendor is itself a fail-closed condition: default to the
    # Anthropic exit-2 hard-block, the most conservative cross-vendor deny.
    return _ENCODERS.get(vendor, encode_anthropic_decision)


def run_hook_client(
    *,
    stdin: TextIO,
    stdout: TextIO,
    socket_path: str,
    vendor: str,
    timeout: float = _DEFAULT_CLIENT_TIMEOUT_SECONDS,
) -> int:
    """Drive one hook invocation: read stdin, forward, encode, return exit code.

    Reads the CLI's tool-request JSON from ``stdin``, forwards it to the bridge
    at ``socket_path``, blocks for the decision (bounded by ``timeout``), encodes
    the result in the vendor-correct shape on ``stdout``, and returns the
    documented exit code. Fail-closed throughout: an unreadable/malformed stdin,
    an unreachable bridge, or a timeout all emit a vendor-correct **deny**.
    """
    encode = _encoder_for(vendor)
    payload = _read_stdin_payload(stdin)
    if payload is None:
        return _emit(stdout, encode(_DENY))
    decision = forward_tool_request(socket_path, payload, timeout=timeout)
    return _emit(stdout, encode(decision))


def craik_hook_main(argv: list[str] | None = None) -> int:
    """Console entrypoint for the ``craik-hook`` script.

    Resolves the socket path and vendor from the environment (set by the gateway
    when it spawns the CLI), reads stdin, and prints the vendor-correct decision.
    A missing socket env is a fail-closed deny.
    """
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] in {"-h", "--help"}:
        sys.stdout.write(
            "craik-hook: CLI pre-tool gating client. Reads a tool-request JSON on "
            "stdin, forwards it to the craik gateway bridge "
            f"(${SOCKET_ENV}), and prints the ${VENDOR_ENV}-correct decision. "
            "Fail-closed: deny on any error.\n"
        )
        return 0
    socket_path = os.environ.get(SOCKET_ENV, "")
    vendor = os.environ.get(VENDOR_ENV, "anthropic")
    timeout = _timeout_from_env(os.environ.get("CRAIK_HOOK_TIMEOUT"))
    if not socket_path:
        # No bridge configured -> fail closed in the vendor-correct shape.
        return _emit(sys.stdout, _encoder_for(vendor)(_DENY))
    return run_hook_client(
        stdin=sys.stdin,
        stdout=sys.stdout,
        socket_path=socket_path,
        vendor=vendor,
        timeout=timeout,
    )


def _timeout_from_env(raw: str | None) -> float:
    if not raw:
        return _DEFAULT_CLIENT_TIMEOUT_SECONDS
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_CLIENT_TIMEOUT_SECONDS


def _read_stdin_payload(stdin: TextIO) -> dict[str, Any] | None:
    try:
        raw = stdin.read()
    except OSError:
        return None
    return _decode_payload(raw)


def _emit(stdout: TextIO, encoded: tuple[str, int]) -> int:
    body, exit_code = encoded
    stdout.write(body)
    return exit_code


__all__ = [
    "SOCKET_ENV",
    "VENDOR_ENV",
    "craik_hook_main",
    "encode_anthropic_decision",
    "encode_google_decision",
    "forward_tool_request",
    "run_hook_client",
]
