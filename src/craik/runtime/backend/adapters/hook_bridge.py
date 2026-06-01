"""Hook-bridge daemon RPC server for CLI live-gating (gateway side).

New, self-contained Phase-5 infrastructure. It is **additive**: nothing in the
live ``execute_prompt`` path calls it yet (that wiring is Task 5.2; the cutover
is a later PR).

:class:`HookBridgeServer` runs inside the craik gateway daemon, listening on a
Unix domain socket. For each forwarded tool-request payload it invokes a
supplied ``decide(payload) -> "allow" | "deny"`` callback and writes back a
**vendor-agnostic transport decision** (JSON ``{"decision": ...}``). The gateway
builds that ``decide`` with ``make_operator_decide`` (Task 5.2, in the sibling
:mod:`craik.runtime.backend.adapters.hook_gating` module), which routes the
request through craik's operator approval flow.

The **client half** -- the ``craik-hook`` console script the CLI's pre-tool hook
invokes (:func:`~craik.runtime.hooks.client.run_hook_client` /
:func:`~craik.runtime.hooks.client.craik_hook_main`), plus the vendor encoders
(:func:`~craik.runtime.hooks.client.encode_anthropic_decision` /
:func:`~craik.runtime.hooks.client.encode_google_decision`) and
:func:`~craik.runtime.hooks.client.forward_tool_request` -- lives in the
dependency-light :mod:`craik.runtime.hooks.client`. It is split out so the
``craik-hook`` console entry imports ONLY stdlib (the hook fires on every CLI
tool call); see that module's docstring. The bridge is vendor-agnostic
transport; the vendor-specific encoding happens client-side.

The transport sentinels ``_ALLOW`` / ``_DENY`` and the gateway env-var names
``SOCKET_ENV`` / ``VENDOR_ENV`` are defined canonically in
:mod:`craik.runtime.hooks.client` (so the client never imports this server
module) and re-exported here for the gateway-side adapters and ``hook_gating``
that import them from this module.

**Open-risk note (fail-closed):** a timeout, dropped connection, unreachable
socket, or malformed decision is resolved as **deny** -- never a silent allow.
"""

from __future__ import annotations

import socket
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Any

# Shared socket wire-framing (single source of truth for both bridge halves;
# stdlib-only so the thin client side stays dependency-light). See the
# ``_transport`` module docstring.
from craik.runtime.hooks._transport import (
    _read_message,
    _write_message,
)

# Canonical definitions live in the thin client so it stays free of this
# (gateway-side) module. Re-exported here for ``hook_gating`` (``_ALLOW`` /
# ``_DENY``) and the CLI gating adapters (``SOCKET_ENV`` / ``VENDOR_ENV``).
from craik.runtime.hooks.client import (
    _ALLOW,
    _DENY,
    SOCKET_ENV,
    VENDOR_ENV,
)


class HookBridgeServer:
    """Unix-socket RPC server that resolves forwarded tool requests to decisions.

    Constructed with a socket path and a ``decide`` callback. Lifecycle is a
    context manager (or explicit :meth:`start` / :meth:`close`); the socket file
    is removed on close. A malformed payload is resolved as a safe-default
    ``deny`` without consulting ``decide``.
    """

    def __init__(
        self,
        socket_path: str,
        *,
        decide: Callable[[dict[str, Any]], str],
        accept_timeout: float | None = None,
    ) -> None:
        self._socket_path = socket_path
        self._decide = decide
        self._accept_timeout = accept_timeout
        self._server: socket.socket | None = None

    def __enter__(self) -> HookBridgeServer:
        self.start()
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        self.close()

    def start(self) -> None:
        """Bind and listen on the Unix socket, creating the socket file."""
        self._unlink_socket()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self._socket_path)
        server.listen(16)
        if self._accept_timeout is not None:
            server.settimeout(self._accept_timeout)
        self._server = server

    def close(self) -> None:
        """Stop listening and remove the socket file (idempotent)."""
        if self._server is not None:
            self._server.close()
            self._server = None
        self._unlink_socket()

    def serve_once(self) -> None:
        """Accept one connection, resolve it, and reply. Used in tests/one-shot."""
        if self._server is None:
            raise RuntimeError("HookBridgeServer.serve_once called before start()")
        conn, _addr = self._server.accept()
        self._handle_connection(conn)

    def serve_forever(self) -> None:
        """Accept and resolve connections until the server socket is closed."""
        while self._server is not None:
            try:
                conn, _addr = self._server.accept()
            except OSError:
                return
            self._handle_connection(conn)

    def _handle_connection(self, conn: socket.socket) -> None:
        try:
            payload = _read_message(conn)
            decision = self._resolve(payload)
            _write_message(conn, {"decision": decision})
        except (OSError, ValueError):
            # A dropped/garbled connection is a fail-closed deny; never raise out
            # of the accept loop on a single bad client.
            try:
                _write_message(conn, {"decision": _DENY})
            except OSError:
                # Best-effort deny reply: the connection is already broken, so
                # the write may fail. The client treats an empty/closed
                # connection as a deny anyway, so there is nothing left to do.
                pass
        finally:
            conn.close()

    def _resolve(self, payload: dict[str, Any] | None) -> str:
        # Malformed payload -> safe-default deny, ``decide`` not consulted.
        if payload is None:
            return _DENY
        try:
            decision = self._decide(payload)
        except Exception:
            # A throwing ``decide`` (the Task 5.2 live operator/policy callback
            # runs on attacker-influenced payloads) is a per-request fail-closed
            # deny -- never a crash that propagates out of ``serve_forever`` and
            # kills the accept loop for every subsequent run. ``BaseException``
            # (KeyboardInterrupt/SystemExit) is intentionally NOT caught.
            return _DENY
        return _ALLOW if decision == _ALLOW else _DENY

    def _unlink_socket(self) -> None:
        path = Path(self._socket_path)
        if path.exists() or path.is_symlink():
            try:
                path.unlink()
            except OSError:
                # Best-effort cleanup: the socket file may already be gone
                # (concurrent close / removed externally); nothing to do.
                pass


__all__ = [
    "SOCKET_ENV",
    "VENDOR_ENV",
    "HookBridgeServer",
]
