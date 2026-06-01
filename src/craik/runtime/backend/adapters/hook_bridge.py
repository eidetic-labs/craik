"""Hook-bridge daemon RPC + ``craik-hook`` client for CLI live-gating.

New, self-contained Phase-5 infrastructure. It is **additive**: nothing in the
live ``execute_prompt`` path calls it yet (that wiring is Task 5.2; the cutover
is a later PR). The two halves:

- :class:`HookBridgeServer` runs inside the craik gateway daemon, listening on a
  Unix domain socket. For each forwarded tool-request payload it invokes a
  supplied ``decide(payload) -> "allow" | "deny"`` callback and writes back a
  **vendor-agnostic transport decision** (JSON ``{"decision": ...}``). The
  gateway builds that ``decide`` with :func:`make_operator_decide` (Task 5.2),
  which routes the request through craik's operator approval flow.
- :func:`run_hook_client` (entrypoint :func:`craik_hook_main`) is the
  ``craik-hook`` console script the CLI's pre-tool hook invokes. It reads the
  CLI's tool-request JSON from stdin, connects to the bridge socket, forwards
  the payload, blocks for the decision, then **encodes it in the VENDOR-CORRECT
  shape** on stdout and returns the documented exit code.

The bridge is vendor-agnostic transport; the vendor-specific encoding happens
client-side via :func:`encode_anthropic_decision` / :func:`encode_google_decision`.
The encoders live HERE (not on the concrete adapters) so the client can import
them without dragging in the whole adapter stack: the client process is a tiny
short-lived hook invocation, and the adapters import heavy event/parser modules.
A concrete adapter that needs an encoder imports it from this module.

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
socket, or malformed decision is resolved as **deny** -- never a silent allow.
"""

from __future__ import annotations

import json
import os
import socket
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    from craik.runtime.backend.events import BackendEvent
    from craik.runtime.reviewing.approvals import ApprovalStore

# Decision vocabulary on the transport (vendor-agnostic).
_ALLOW = "allow"
_DENY = "deny"

# The CLI pre-tool hook's documented blocking timeout is 600 s
# (vendor-capabilities.md line 47). The client default is well under that so a
# stuck bridge fails closed long before the CLI's own timeout fires.
_MAX_HOOK_TIMEOUT_SECONDS = 600.0
_DEFAULT_CLIENT_TIMEOUT_SECONDS = 30.0

# Env vars the gateway sets when it spawns the CLI so the hook script can find
# the bridge and know which vendor dialect to emit.
SOCKET_ENV = "CRAIK_HOOK_SOCKET"
VENDOR_ENV = "CRAIK_HOOK_VENDOR"

# Default deny rationale surfaced to the CLI/operator on a fail-closed decision.
_DENY_REASON = "craik withheld authorization for this tool call"

# Transport framing: newline-delimited UTF-8 JSON, one message per direction.
_RECV_CHUNK = 65536


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
                pass


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
    import sys

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


def _decode_payload(raw: str) -> dict[str, Any] | None:
    if not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _emit(stdout: TextIO, encoded: tuple[str, int]) -> int:
    body, exit_code = encoded
    stdout.write(body)
    return exit_code


def _read_message(conn: socket.socket) -> dict[str, Any] | None:
    buffer = bytearray()
    while b"\n" not in buffer:
        chunk = conn.recv(_RECV_CHUNK)
        if not chunk:
            break
        buffer.extend(chunk)
    raw = bytes(buffer).split(b"\n", 1)[0].decode("utf-8", errors="replace")
    return _decode_payload(raw)


def _write_message(conn: socket.socket, payload: dict[str, Any]) -> None:
    conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))


# ---------------------------------------------------------------------------
# Gateway-side operator-decision factory (Phase 5 Task 5.2)
# ---------------------------------------------------------------------------
# This is the ``decide`` half: :class:`HookBridgeServer` is constructed with a
# ``decide(payload) -> "allow" | "deny"`` callback, and :func:`make_operator_decide`
# builds that callback so a forwarded CLI tool-request resolves through craik's
# **operator approval flow** -- the same ``approval.requested`` -> TUI modal ->
# ``approval.decide`` -> ``approval.resolved`` cycle the gateway already runs
# (``session.py`` / ``jsonl.py``).
#
# It lives HERE (not on a new module) because it IS the bridge's decide factory
# -- and a new ``backend/`` or ``adapters/`` module would breach the 15-file
# runtime-layout guard. The heavy ``events`` / ``approvals`` imports it needs are
# kept FUNCTION-LOCAL so the short-lived ``craik-hook`` client process (which only
# touches the encoders + :func:`run_hook_client` above) never drags them in --
# preserving this module's "tiny client, heavy gateway" split.
#
# Composability, not live wiring (scope: PR A): this delivers a tested unit. It
# does NOT start the bridge in the live ``execute_prompt`` loop and does NOT touch
# any adapter ``spawn``; that cutover is PR B. The ``resolve_lookup`` seam keeps
# it testable without the live run loop: a ``(approval_id) -> "allow" | "deny" |
# None`` probe over the approval store's resolution state. The operator resolves
# over JSONL via ``approval.decide`` -> ``decide_approval`` (records the delegation
# ``status="resolved"`` with a ``resolution`` ``"approved: ..."`` / ``"denied:
# ..."``); PR B supplies a ``resolve_lookup`` that reads that state, and tests
# inject a pre-queued decision through the same seam.
#
# Fail-closed: a timeout with no resolution, or ANY exception from
# ``open_approval_request`` / ``resolve_lookup`` / ``emit``, resolves to **deny**
# -- matching the bridge's own contract.

# Operator-flow defaults for an opened CLI-gate approval request.
_GATE_TASK_ID = "task_gateway_cli_gate"
_GATE_REQUESTED_BY = "craik:cli-hook-bridge"
_GATE_RISK = "CLI tool call awaiting operator authorization"
_GATE_POLICY = "strict"
_GATE_RETRY_PATH = "approve in the TUI modal, then the CLI retries the blocked tool call"

# Resolution poll cadence; the wait is bounded by the caller's ``timeout``.
_POLL_INTERVAL_SECONDS = 0.01


def make_operator_decide(
    *,
    store: ApprovalStore,
    emit: Callable[[BackendEvent], None],
    timeout: float,
    resolve_lookup: Callable[[str], str | None],
) -> Callable[[dict[str, Any]], str]:
    """Build the bridge ``decide`` callback that routes to operator approval.

    The returned ``decide(payload)`` derives a tool-request summary, opens an
    approval request in ``store``, EMITS an ``approval.requested`` event (carrying
    the real ``approval_id``) so the TUI surfaces the modal, then BLOCKS until the
    operator resolves it -- polling ``resolve_lookup`` for ``"allow"`` / ``"deny"``,
    bounded by ``timeout`` -- and returns that decision. On timeout or ANY error
    it returns ``"deny"`` (fail-closed, matching the bridge).

    ``resolve_lookup`` is the injectable seam over the approval store's resolution
    state (see the section comment above).
    """
    # Function-local: keep the short-lived client process free of these imports.
    from craik.runtime.backend.events import approval_requested_event
    from craik.runtime.reviewing.approvals import open_approval_request

    def decide(payload: dict[str, Any]) -> str:
        try:
            tool, target, command = _summarize_tool_request(payload)
            approval_id = _new_gate_approval_id()
            open_approval_request(
                store,
                approval_id=approval_id,
                task_id=_GATE_TASK_ID,
                capability=tool,
                target=target,
                risk=_GATE_RISK,
                policy=_GATE_POLICY,
                requested_by=_GATE_REQUESTED_BY,
                retry_path=_GATE_RETRY_PATH,
            )
            event = approval_requested_event(
                message=f"Approve {tool} on {target}?",
                source="gateway",
                tool=tool,
                target=target,
                reason=command,
            )
            # Carry the real approval id so the TUI's ``approval.decide`` round-trip
            # targets THIS request (the builder omits it; the contract permits the
            # extra key and the data dict is mutable).
            event.data["approval_id"] = approval_id
            emit(event)
        except Exception:
            # Could not open/surface the request -> fail-closed deny: a tool call
            # must never run because craik failed to ask the operator.
            return _DENY
        return _wait_for_operator_decision(approval_id, resolve_lookup, timeout)

    return decide


def _summarize_tool_request(payload: dict[str, Any]) -> tuple[str, str, str | None]:
    """Derive ``(tool, target, command)`` from a vendor CLI tool-request payload.

    Tolerant of the two dialects: the Anthropic/Codex hook payload uses
    ``tool_name`` + a ``tool_input`` object (``command`` / ``file_path`` /
    ``path``); the Gemini ``BeforeTool`` payload uses ``name`` + ``input``. An
    unknown shape degrades to a generic ``"tool"`` -- the request is still opened
    and surfaced (fail-closed governance applies regardless of summary fidelity).
    """
    tool = _first_str(payload.get("tool_name"), payload.get("name")) or "tool"
    raw_input = payload.get("tool_input")
    if not isinstance(raw_input, dict):
        candidate = payload.get("input")
        raw_input = candidate if isinstance(candidate, dict) else {}
    command = _first_str(payload.get("command"), raw_input.get("command"))
    target = (
        _first_str(raw_input.get("file_path"), raw_input.get("path"), payload.get("target"))
        or command
        or tool
    )
    return tool, target, command


def _wait_for_operator_decision(
    approval_id: str,
    resolve_lookup: Callable[[str], str | None],
    timeout: float,
) -> str:
    """Poll ``resolve_lookup`` until a decision lands or ``timeout`` elapses.

    Returns the operator's ``"allow"`` / ``"deny"``. A non-positive timeout, an
    elapsed deadline with no decision, or any exception from the lookup is a
    fail-closed ``"deny"``.
    """
    deadline = time.monotonic() + max(timeout, 0.0)
    while True:
        try:
            decision = resolve_lookup(approval_id)
        except Exception:
            return _DENY
        if decision == _ALLOW:
            return _ALLOW
        if decision == _DENY:
            return _DENY
        if time.monotonic() >= deadline:
            return _DENY
        time.sleep(_POLL_INTERVAL_SECONDS)


def _new_gate_approval_id() -> str:
    return f"approval_cli_gate_{uuid.uuid4().hex}"


def _first_str(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value
    return None


__all__ = [
    "HookBridgeServer",
    "craik_hook_main",
    "encode_anthropic_decision",
    "encode_google_decision",
    "forward_tool_request",
    "make_operator_decide",
    "run_hook_client",
]
