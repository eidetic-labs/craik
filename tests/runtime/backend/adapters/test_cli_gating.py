"""Tests for Phase 5 Task 5.2: CLI adapter hook config + gateway operator-decide.

Component-level. Two concerns:

1. ``make_operator_decide`` (in ``craik.runtime.backend.adapters.hook_gating``): the
   gateway factory that turns a forwarded tool-request payload into an
   ``allow``/``deny`` decision by opening an approval request, emitting an
   ``approval.requested`` event (so the TUI shows the modal), and BLOCKING on the
   operator's resolution (bounded by a timeout, fail-closed). A pre-queued
   operator decision is injected via the ``resolve_lookup`` seam so the unit can
   exercise allow / deny / timeout without the live gateway run loop.
2. The CLI gating adapters' hook config: ``AnthropicCLI`` registers ``craik-hook``
   as the PreToolUse hook with ``CRAIK_HOOK_VENDOR=anthropic``; ``GoogleCLI``
   registers it as the BeforeTool hook with ``CRAIK_HOOK_VENDOR=google`` (and
   keeps ``GEMINI_CLI_TRUST_WORKSPACE``); ``OpenAICLI`` has NO hook config
   (observe-only, verified negative).

Plus a bridge integration: a ``HookBridgeServer`` whose ``decide`` is the factory
output, fed a queued deny over the real socket, returns ``deny`` on the transport
and emits the ``approval.requested`` event -- proving bridge<->operator wiring
without a live CLI.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from craik.contracts.models import HumanDelegationPoint
from craik.runtime.backend.adapters.anthropic_cli import AnthropicCLI
from craik.runtime.backend.adapters.google_cli import GoogleCLI
from craik.runtime.backend.adapters.hook_bridge import (
    SOCKET_ENV,
    VENDOR_ENV,
    HookBridgeServer,
)
from craik.runtime.backend.adapters.hook_gating import (
    hook_bridge_session,
    make_operator_decide,
    make_store_resolve_lookup,
)
from craik.runtime.backend.adapters.openai_cli import OpenAICLI
from craik.runtime.backend.events import BackendEvent, validate_event
from craik.runtime.hooks.client import forward_tool_request
from craik.runtime.paths import ensure_craik_home
from craik.runtime.reviewing.approvals import (
    decide_approval,
    open_approval_request,
)
from craik.runtime.store import LocalStore


class _FakeApprovalStore:
    """Minimal in-memory ``ApprovalStore`` for the decide factory under test."""

    def __init__(self) -> None:
        self.delegations: dict[str, HumanDelegationPoint] = {}

    def put_human_delegation(self, delegation: HumanDelegationPoint) -> None:
        self.delegations[delegation.id] = delegation

    def get_human_delegation(self, delegation_id: str) -> HumanDelegationPoint | None:
        return self.delegations.get(delegation_id)

    def list_human_delegations(self) -> list[HumanDelegationPoint]:
        return list(self.delegations.values())

    def put_receipt(self, receipt: object) -> object:  # pragma: no cover - unused here
        return receipt


def _collector() -> tuple[list[BackendEvent], object]:
    events: list[BackendEvent] = []
    return events, events.append


_BASH_PAYLOAD = {"tool_name": "Bash", "command": "rm -rf /tmp/x", "session_id": "s1"}


def test_decide_emits_approval_requested_and_allows_on_queued_allow() -> None:
    store = _FakeApprovalStore()
    events, emit = _collector()
    decide = make_operator_decide(
        store=store,
        emit=emit,
        timeout=2.0,
        resolve_lookup=lambda _approval_id: "allow",
    )

    decision = decide(_BASH_PAYLOAD)

    assert decision == "allow"
    requested = [e for e in events if e.type == "approval.requested"]
    assert len(requested) == 1
    # The emitted request carries the REAL approval id that was opened.
    approval_id = requested[0].data["approval_id"]
    assert approval_id in store.delegations
    # The derived tool summary surfaces the tool + target/command.
    assert requested[0].data.get("tool") == "Bash"


def test_approval_requested_event_with_extra_approval_id_passes_contract() -> None:
    # ``make_operator_decide`` adds an EXTRA ``approval_id`` key to the
    # ``approval.requested`` event's ``data`` (the builder omits it). Pin that the
    # resulting event still PASSES the gateway event contract, so a future
    # strict-additional-properties change can't silently break the gating wiring.
    store = _FakeApprovalStore()
    events, emit = _collector()
    decide = make_operator_decide(
        store=store,
        emit=emit,
        timeout=0.05,
        resolve_lookup=lambda _approval_id: None,
    )

    decide(_BASH_PAYLOAD)

    requested = [e for e in events if e.type == "approval.requested"]
    assert len(requested) == 1
    event = requested[0]
    # The extra key is present (the contract-pin's reason for existing).
    assert "approval_id" in event.data
    # ... and the full event (with that extra key) satisfies the contract.
    validate_event(event)


def test_decide_denies_on_queued_deny() -> None:
    store = _FakeApprovalStore()
    events, emit = _collector()
    decide = make_operator_decide(
        store=store,
        emit=emit,
        timeout=2.0,
        resolve_lookup=lambda _approval_id: "deny",
    )

    decision = decide(_BASH_PAYLOAD)

    assert decision == "deny"
    assert any(e.type == "approval.requested" for e in events)


def test_decide_denies_on_timeout_with_no_decision() -> None:
    store = _FakeApprovalStore()
    events, emit = _collector()
    decide = make_operator_decide(
        store=store,
        emit=emit,
        timeout=0.05,
        resolve_lookup=lambda _approval_id: None,
    )

    decision = decide(_BASH_PAYLOAD)

    # No operator resolution within the (short) timeout -> fail-closed deny,
    # but the request WAS still surfaced to the operator.
    assert decision == "deny"
    assert any(e.type == "approval.requested" for e in events)


def test_decide_denies_when_resolve_lookup_raises() -> None:
    store = _FakeApprovalStore()
    events, emit = _collector()

    def boom(_approval_id: str) -> str | None:
        raise RuntimeError("store exploded")

    decide = make_operator_decide(
        store=store,
        emit=emit,
        timeout=0.5,
        resolve_lookup=boom,
    )

    assert decide(_BASH_PAYLOAD) == "deny"


def test_decide_defers_to_queued_operator_decision_recorded_in_store() -> None:
    # The "decide that defers to a queued operator decision": the operator's
    # resolution is recorded in the store (status -> resolved) BEFORE decide
    # polls, exactly as the live approval.decide -> decide_approval cycle leaves
    # it. A store-reading resolve_lookup then maps it to allow/deny.
    store = _FakeApprovalStore()
    events, emit = _collector()

    def resolve_from_store(approval_id: str) -> str | None:
        delegation = store.get_human_delegation(approval_id)
        if delegation is None or delegation.status != "resolved":
            return None
        resolution = delegation.resolution or ""
        if resolution.startswith("approved"):
            return "allow"
        if resolution.startswith("denied"):
            return "deny"
        return None

    captured: dict[str, str] = {}

    def emit_and_resolve(event: BackendEvent) -> None:
        events.append(event)
        if event.type == "approval.requested":
            # Simulate the operator approving via the existing resolve cycle:
            # mark the delegation resolved, as decide_approval would.
            approval_id = str(event.data["approval_id"])
            captured["approval_id"] = approval_id
            delegation = store.get_human_delegation(approval_id)
            assert delegation is not None
            store.put_human_delegation(
                delegation.model_copy(
                    update={
                        "status": "resolved",
                        "resolution": "approved: operator ok. Retry path: -",
                        "resolved_at": datetime.now(UTC),
                    }
                )
            )

    decide = make_operator_decide(
        store=store,
        emit=emit_and_resolve,
        timeout=2.0,
        resolve_lookup=resolve_from_store,
    )

    assert decide(_BASH_PAYLOAD) == "allow"
    assert captured["approval_id"] in store.delegations


def test_bridge_integration_queued_deny(tmp_path: Path) -> None:
    socket_path = tmp_path / "bridge.sock"
    store = _FakeApprovalStore()
    events, emit = _collector()
    decide = make_operator_decide(
        store=store,
        emit=emit,
        timeout=2.0,
        resolve_lookup=lambda _approval_id: "deny",
    )
    with HookBridgeServer(str(socket_path), decide=decide) as server:
        thread = threading.Thread(target=server.serve_once, daemon=True)
        thread.start()
        decision = forward_tool_request(str(socket_path), _BASH_PAYLOAD, timeout=2.0)
        thread.join(timeout=2.0)

    assert decision == "deny"
    assert any(e.type == "approval.requested" for e in events)


# --- Adapter hook config ---------------------------------------------------


def test_anthropic_cli_registers_craik_hook_pre_tool_use() -> None:
    adapter = AnthropicCLI()
    config = adapter.pre_tool_use_hook_config

    assert config["event"] == "PreToolUse"
    # craik-hook is the registered hook command.
    assert "craik-hook" in str(config["command"])
    # The vendor dialect is anthropic, passed via env.
    assert config["env"][VENDOR_ENV] == "anthropic"
    # The socket env is referenced (the live spawn substitutes the real path).
    assert SOCKET_ENV in config["env"]


def test_google_cli_registers_craik_hook_before_tool() -> None:
    adapter = GoogleCLI()
    config = adapter.before_tool_hook_config

    assert config["event"] == "BeforeTool"
    assert "craik-hook" in str(config["command"])
    assert config["env"][VENDOR_ENV] == "google"
    assert SOCKET_ENV in config["env"]
    # Workspace trust is preserved alongside the hook env (load-bearing).
    assert config["env"]["GEMINI_CLI_TRUST_WORKSPACE"] == "true"


def test_openai_cli_has_no_hook_config() -> None:
    adapter = OpenAICLI()
    # Observe-only: the codex pre-tool hook does not fire, so there is NO hook
    # config to register (verified negative, vendor-capabilities.md § OpenAI).
    assert not hasattr(adapter, "pre_tool_use_hook_config")
    assert not hasattr(adapter, "before_tool_hook_config")
    assert adapter.supports_live_gating() is False


# --- make_store_resolve_lookup (Task 5.6) ----------------------------------


def _open_gate(store: LocalStore, approval_id: str) -> None:
    open_approval_request(
        store,
        approval_id=approval_id,
        task_id="task_gate",
        capability="Bash",
        target="rm -rf /tmp/x",
        risk="r",
        policy="strict",
        requested_by="craik:cli-hook-bridge",
        retry_path="approve in TUI",
    )


def test_store_resolve_lookup_approved_returns_allow(tmp_path: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        _open_gate(store, "approval_a")
        lookup = make_store_resolve_lookup(store)
        # Pending before any decision.
        assert lookup("approval_a") is None
        decide_approval(store, "approval_a", decision="approved", operator="op", reason="ok")
        assert lookup("approval_a") == "allow"
    finally:
        store.close()


def test_store_resolve_lookup_denied_returns_deny(tmp_path: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        _open_gate(store, "approval_d")
        lookup = make_store_resolve_lookup(store)
        decide_approval(store, "approval_d", decision="denied", operator="op", reason="no")
        assert lookup("approval_d") == "deny"
    finally:
        store.close()


def test_store_resolve_lookup_unknown_returns_none(tmp_path: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        lookup = make_store_resolve_lookup(store)
        # An id with no opened delegation is pending/unknown -> keep blocking.
        assert lookup("approval_missing") is None
    finally:
        store.close()


# --- hook_bridge_session end-to-end (Task 5.6) ------------------------------
#
# These drive the FULL loop in-process with no real CLI: a tool-request is
# forwarded to the yielded socket from a worker thread (the ``craik-hook`` client
# transport), it BLOCKS in ``decide`` until the operator resolves the gate via
# the real ``decide_approval`` cycle, and the store ``resolve_lookup`` unblocks
# it. The store is a thread-safe in-memory ``ApprovalStore`` (the real
# ``LocalStore``'s SQLite connection is single-thread-bound, and the live 5.7
# gateway services approvals concurrently -- see ``hook_bridge_session``'s 5.7
# concurrency note); ``open_approval_request`` / ``decide_approval`` are the REAL
# helpers, so the recorded resolution state is exactly what the gateway writes.


class _LockedApprovalStore(_FakeApprovalStore):
    """Thread-safe in-memory ``ApprovalStore`` for the cross-thread bridge test."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()

    def put_human_delegation(self, delegation: HumanDelegationPoint) -> None:
        with self._lock:
            super().put_human_delegation(delegation)

    def get_human_delegation(self, delegation_id: str) -> HumanDelegationPoint | None:
        with self._lock:
            return super().get_human_delegation(delegation_id)

    def list_human_delegations(self) -> list[HumanDelegationPoint]:
        with self._lock:
            return super().list_human_delegations()

    def put_receipt(self, receipt):  # type: ignore[no-untyped-def]
        return receipt


def _forward_in_thread(
    socket_path: str, payload: dict[str, object], result: dict[str, str]
) -> threading.Thread:
    def _run() -> None:
        result["decision"] = forward_tool_request(socket_path, payload, timeout=5.0)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def _await_one_open_gate(store: _FakeApprovalStore, deadline: float) -> str | None:
    while time.monotonic() < deadline:
        for delegation in store.list_human_delegations():
            if delegation.kind == "approval" and delegation.status == "open":
                return delegation.id
        time.sleep(0.01)
    return None


def test_hook_bridge_session_blocks_then_allows_on_resolution() -> None:
    store = _LockedApprovalStore()
    events: list[BackendEvent] = []
    captured_socket: dict[str, str] = {}
    with hook_bridge_session(store=store, emit=events.append, timeout=5.0, vendor="anthropic") as (
        socket_path,
        overlay,
    ):
        captured_socket["path"] = socket_path
        # The overlay carries the bridge address + vendor the CLI spawn merges.
        assert overlay[SOCKET_ENV] == socket_path
        assert overlay[VENDOR_ENV] == "anthropic"

        result: dict[str, str] = {}
        thread = _forward_in_thread(socket_path, dict(_BASH_PAYLOAD), result)

        # The hook BLOCKS pending: no decision while the gate is unresolved.
        approval_id = _await_one_open_gate(store, time.monotonic() + 3.0)
        assert approval_id is not None
        assert "decision" not in result

        # The operator approves via the same decide_approval cycle the gateway
        # drives; the session's store resolve_lookup then unblocks the hook.
        decide_approval(store, approval_id, decision="approved", operator="op", reason="ok")
        thread.join(timeout=5.0)
        assert result["decision"] == "allow"

    # approval.requested was emitted carrying the REAL approval id.
    requested = [e for e in events if e.type == "approval.requested"]
    assert len(requested) == 1
    assert requested[0].data["approval_id"] == approval_id
    # The socket is cleaned up on session exit.
    assert not Path(captured_socket["path"]).exists()


def test_hook_bridge_session_denied_resolution_returns_deny() -> None:
    store = _LockedApprovalStore()
    events: list[BackendEvent] = []
    with hook_bridge_session(store=store, emit=events.append, timeout=5.0) as (
        socket_path,
        _overlay,
    ):
        result: dict[str, str] = {}
        thread = _forward_in_thread(socket_path, dict(_BASH_PAYLOAD), result)
        approval_id = _await_one_open_gate(store, time.monotonic() + 3.0)
        assert approval_id is not None
        decide_approval(store, approval_id, decision="denied", operator="op", reason="no")
        thread.join(timeout=5.0)
        assert result["decision"] == "deny"


def test_hook_bridge_session_times_out_to_deny() -> None:
    store = _LockedApprovalStore()
    events: list[BackendEvent] = []
    socket_path_holder: dict[str, str] = {}
    # A short bridge timeout: a never-resolved request fails closed to deny.
    with hook_bridge_session(store=store, emit=events.append, timeout=0.2) as (
        socket_path,
        _overlay,
    ):
        socket_path_holder["path"] = socket_path
        decision = forward_tool_request(socket_path, dict(_BASH_PAYLOAD), timeout=5.0)
        assert decision == "deny"
        assert any(e.type == "approval.requested" for e in events)
    assert not Path(socket_path_holder["path"]).exists()
