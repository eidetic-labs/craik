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

Composability, not live wiring (scope: PR A): this delivers a tested unit. It
does NOT start the bridge in the live ``execute_prompt`` loop and does NOT touch
any adapter ``spawn``; that cutover is PR B. The ``resolve_lookup`` seam keeps
it testable without the live run loop: a ``(approval_id) -> "allow" | "deny" |
None`` probe over the approval store's resolution state. The operator resolves
over JSONL via ``approval.decide`` -> ``decide_approval`` (records the delegation
``status="resolved"`` with a ``resolution`` ``"approved: ..."`` / ``"denied:
..."``); PR B supplies a ``resolve_lookup`` that reads that state, and tests
inject a pre-queued decision through the same seam.

Fail-closed: a timeout with no resolution, or ANY exception from
``open_approval_request`` / ``resolve_lookup`` / ``emit``, resolves to **deny**
-- matching the bridge's own contract.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from craik.runtime.backend.adapters.hook_bridge import _ALLOW, _DENY

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


__all__ = ["make_operator_decide"]
