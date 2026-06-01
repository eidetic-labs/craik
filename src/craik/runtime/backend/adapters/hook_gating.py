"""Gateway-side operator-decision factory for the hook bridge (Phase 5 Task 5.2).

This is the ``decide`` half of the hook bridge:
:class:`~craik.runtime.backend.adapters.hook_bridge.HookBridgeServer` is
constructed with a ``decide(payload) -> "allow" | "deny"`` callback, and
:func:`make_operator_decide` builds that callback so a forwarded CLI tool-request
resolves through craik's **operator approval flow** -- the same
``approval.requested`` -> TUI modal -> ``approval.decide`` -> ``approval.resolved``
cycle the gateway already runs (``session.py`` / ``jsonl.py``).

It lives in its OWN module (not on ``hook_bridge``) so the transport file stays
within the file-size budget. The dependency is one-way: this module imports the
``_ALLOW`` / ``_DENY`` transport sentinels from ``hook_bridge``; ``hook_bridge``
does NOT import this module. That keeps the short-lived ``craik-hook`` client
process (which only touches the encoders + ``run_hook_client`` in ``hook_bridge``)
free of the gating / approvals stack -- preserving the "tiny client, heavy
gateway" split. The heavy ``events`` / ``approvals`` imports are kept
FUNCTION-LOCAL for the same reason.

Live wiring (PR B landed): the bridge IS started in the live ``execute_prompt``
loop -- ``gateway.cli_gating_loop.gated_cli_run_session`` runs a gated CLI
adapter off the stdin thread inside a ``hook_bridge_session``. The
``resolve_lookup`` seam also keeps this unit testable without the live run loop:
a ``(approval_id) -> "allow" | "deny" | None`` probe over the approval store's
resolution state. The operator resolves over JSONL via ``approval.decide`` ->
``decide_approval`` (records the delegation ``status="resolved"`` with a
``resolution`` ``"approved: ..."`` / ``"denied: ..."``); the live driver supplies
a ``resolve_lookup`` that reads that state, and tests inject a pre-queued
decision through the same seam.

Fail-closed: a timeout with no resolution, or ANY exception from
``open_approval_request`` / ``resolve_lookup`` / ``emit``, resolves to **deny**
-- matching the bridge's own contract.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from craik.runtime.backend.adapters.hook_bridge import (
    SOCKET_ENV,
    VENDOR_ENV,
    HookBridgeServer,
)

# The transport sentinels are DEFINED in the thin client (their canonical home);
# import them from there rather than via ``hook_bridge``'s re-export so the
# private names resolve cleanly (``hook_bridge`` does not list them in
# ``__all__``). Matches the documented canonical-source split.
from craik.runtime.hooks.client import _ALLOW, _DENY

if TYPE_CHECKING:
    from craik.runtime.backend.events import BackendEvent
    from craik.runtime.reviewing.approvals import ApprovalStore

# Operator-flow defaults for an opened CLI-gate approval request.
_GATE_TASK_ID = "task_gateway_cli_gate"
_GATE_REQUESTED_BY = "craik:cli-hook-bridge"
_GATE_RISK = "CLI tool call awaiting operator authorization"
_GATE_POLICY = "strict"
_GATE_RETRY_PATH = "approve in the TUI modal, then the CLI retries the blocked tool call"

# Resolution poll cadence; the wait is bounded by the caller's ``timeout``.
_POLL_INTERVAL_SECONDS = 0.01

# The two ``resolution``-prefix tokens ``decide_approval`` writes (see
# ``reviewing.approvals.decide_approval``: ``resolution = f"{decision}: ..."``
# with ``decision`` one of ``"approved"`` / ``"denied"``). They survive
# ``sanitize_runtime_text`` unchanged (no control chars / backticks / ``##``), so
# the store-reading ``resolve_lookup`` keys off them.
_RESOLVED_APPROVED_PREFIX = "approved"
_RESOLVED_DENIED_PREFIX = "denied"

# Default bridge-session shutdown join bound: the background accept loop returns
# promptly once ``close()`` drops the server socket, but the join is bounded so a
# wedged handler can never hang gateway teardown.
_BRIDGE_JOIN_SECONDS = 5.0

# Hook-bridge operator-decision timeout default for a live gate. Well under the
# CLI hook's own documented 600 s ceiling so a stuck operator/bridge fails closed
# before the CLI's timeout fires (see ``hooks.client._MAX_HOOK_TIMEOUT_SECONDS``).
_DEFAULT_GATE_TIMEOUT_SECONDS = 300.0


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


def make_store_resolve_lookup(store: ApprovalStore) -> Callable[[str], str | None]:
    """Build the real ``resolve_lookup`` over an approval store's resolution state.

    Returns ``(approval_id) -> "allow" | "deny" | None``: it reads the delegation
    from ``store`` and maps its recorded resolution to a bridge decision, closing
    the live loop the gateway already drives -- operator ``approval.decide`` (over
    JSONL) -> ``approvals_decide_result`` -> ``decide_approval`` records the
    delegation ``status="resolved"`` with a ``resolution`` of ``"approved: ..."``
    / ``"denied: ..."``; this lookup parses that exact prefix.

    Returns ``None`` (still pending / unknown) when the delegation is missing, is
    not an ``approval``, is not yet ``resolved``, or carries an unrecognized
    resolution -- so :func:`_wait_for_operator_decision` keeps blocking rather than
    treating an indeterminate state as a decision. Any store error surfaces as a
    raised exception, which the caller's poll loop already treats as fail-closed
    ``deny``.
    """

    def resolve_lookup(approval_id: str) -> str | None:
        delegation = store.get_human_delegation(approval_id)
        if delegation is None or delegation.kind != "approval":
            return None
        if delegation.status != "resolved":
            return None
        resolution = delegation.resolution or ""
        if resolution.startswith(_RESOLVED_APPROVED_PREFIX):
            return _ALLOW
        if resolution.startswith(_RESOLVED_DENIED_PREFIX):
            return _DENY
        return None

    return resolve_lookup


@contextmanager
def hook_bridge_session(
    *,
    store: ApprovalStore,
    emit: Callable[[BackendEvent], None],
    env: dict[str, str] | None = None,
    timeout: float = _DEFAULT_GATE_TIMEOUT_SECONDS,
    vendor: str = "anthropic",
) -> Iterator[tuple[str, dict[str, str]]]:
    """Run a live hook-bridge for one gated CLI run; yield ``(socket_path, overlay)``.

    Starts a :class:`HookBridgeServer` bound to a real operator ``decide``
    (``make_operator_decide`` over ``make_store_resolve_lookup(store)``) on a
    background daemon thread, on a per-run Unix socket under a private temp dir,
    and yields the socket path plus the env overlay the CLI spawn MUST merge::

        {CRAIK_HOOK_SOCKET: <socket_path>, CRAIK_HOOK_VENDOR: <vendor>}

    On exit (normal / interrupt / timeout / exception) it stops the server (drops
    the listening socket, ending the accept loop), joins the background thread
    bounded by :data:`_BRIDGE_JOIN_SECONDS`, and unlinks the socket + its temp
    dir. Cleanup never converts the fail-closed default: a hook firing during or
    after teardown finds no socket and the client resolves that to ``deny``
    (matching the bridge/decide contract); the operator-decision timeout is
    likewise a ``deny`` inside ``decide``.

    .. note:: **Concurrency requirement (live wiring).** This helper only STARTS
       the bridge; it does not run the adapter. The live gate is two concurrent
       loops sharing this ``store``: (a) the gateway's JSONL stdin loop must KEEP
       READING ``approval.decide`` messages -> ``decide_approval`` (which records
       the resolution this session's ``resolve_lookup`` reads), WHILE (b) the
       gated CLI subprocess runs and its hook blocks in ``decide`` on the bridge
       thread. Therefore the gated adapter MUST run OFF the stdin-reading thread
       (the CLI run on a worker thread while the gateway services approvals) --
       otherwise ``decide`` blocks forever waiting for a resolution the stalled
       stdin loop can never deliver (self-deadlock). The
       ``gateway.cli_gating_loop.gated_cli_run_session`` driver now satisfies this:
       it runs the gated adapter on a worker thread while the stdin loop keeps
       servicing approvals. The bridge ``decide`` callback is already invoked on
       the bridge's own accept thread here.

       SECOND constraint -- store thread-affinity: ``decide`` calls
       ``open_approval_request`` (and ``resolve_lookup`` calls
       ``get_human_delegation``) on the BRIDGE accept thread, while the gateway
       writes the resolution (``decide_approval``) on the stdin thread. The real
       ``LocalStore`` wraps a ``sqlite3`` connection that is single-thread-bound
       (``check_same_thread`` default), so the driver does NOT share one
       ``LocalStore`` connection across the bridge thread and the stdin thread --
       it gives the bridge its own store handle (a separate connection over the
       SAME on-disk Craik home, opened ``same_thread=False``), so both threads see
       each other's writes while respecting SQLite's thread affinity.
    """
    socket_dir = Path(tempfile.mkdtemp(prefix="craik-hook-"))
    socket_path = str(socket_dir / "bridge.sock")
    decide = make_operator_decide(
        store=store,
        emit=emit,
        timeout=timeout,
        resolve_lookup=make_store_resolve_lookup(store),
    )
    server = HookBridgeServer(socket_path, decide=decide)
    server.start()
    thread = threading.Thread(
        target=server.serve_forever,
        name="craik-hook-bridge",
        daemon=True,
    )
    thread.start()
    overlay = {SOCKET_ENV: socket_path, VENDOR_ENV: vendor}
    try:
        yield socket_path, overlay
    finally:
        # Stop the server FIRST: closing the listening socket makes the blocking
        # ``accept()`` raise ``OSError``, so ``serve_forever`` returns and the
        # thread can be joined. Cleanup is best-effort + fail-closed: a socket
        # already gone simply leaves nothing to remove.
        server.close()
        thread.join(timeout=_BRIDGE_JOIN_SECONDS)
        shutil.rmtree(socket_dir, ignore_errors=True)


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
    "hook_bridge_session",
    "make_operator_decide",
    "make_store_resolve_lookup",
]
