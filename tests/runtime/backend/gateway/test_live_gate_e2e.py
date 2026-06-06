"""Wire-T4: end-to-end live gate round-trip via the REAL bridge + ``craik-hook``.

This is the automatable core of the deferred "live eyeball". It proves craik's
live gating works END-TO-END through the REAL hook bridge AND the REAL
``craik-hook`` client -- WITHOUT a real vendor binary. A fake "CLI subprocess"
invokes the actual ``craik_hook_main()`` console entrypoint (resolving the socket
+ vendor from the environment exactly as the spawned vendor CLI's PreToolUse hook
would), forwarding a tool-request JSON on stdin to the live bridge socket and
honoring the allow/deny it returns.

The full real path exercised here:

    fake CLI run (worker thread)
      -> craik_hook_main() [REAL client: stdin JSON, CRAIK_HOOK_SOCKET/VENDOR]
        -> hook bridge Unix socket [REAL HookBridgeServer]
          -> make_operator_decide [REAL: opens approval, emits approval.requested,
             blocks on the store resolve_lookup]
        <- operator resolves via decide_approval [REAL operator-decide seam,
           records the operator-attributed CapabilityReceipt]
      <- client encodes the VENDOR-CORRECT decision (allow exit 0 / deny exit 2)

Nothing here is mocked along that path: the bridge, the operator-decide factory,
the store, and the client are all the production objects. Only the "vendor CLI"
is faked -- and even it calls the real client.

Three cases, matching the operator-runtime contract:

* **approve** -> client returns ALLOW (exit 0, allow JSON) + an operator-attributed
  ``CapabilityReceipt`` is recorded (``operator_subject`` set, the live-gating
  path's attribution).
* **deny** -> client returns DENY (exit 2, deny JSON) + a denial receipt.
* **fail-closed** -> no socket / unreachable bridge -> client returns DENY
  (never a silent allow).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from craik.runtime.backend.events import BackendEvent
from craik.runtime.backend.gateway.cli_gating_loop import gated_cli_run_session
from craik.runtime.hooks.client import (
    SOCKET_ENV,
    VENDOR_ENV,
)
from craik.runtime.reviewing.approvals import decide_approval
from craik.runtime.store import LocalStore

# The Anthropic tool-request payload shape the PreToolUse hook receives on stdin.
_TOOL_PAYLOAD = {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}

# The operator subject recorded on the live-gating decision receipt (the gateway
# attributes the operator on the same ``decide_approval`` seam).
_OPERATOR = "user:e2e"

# The REAL ``craik-hook`` console entry the vendor CLI would invoke as its
# PreToolUse/BeforeTool command. Resolve it the way the vendor CLI does: off
# PATH. If it is not installed (editable install without the console script) the
# E2E tests can't exercise the real client binary, so they skip rather than
# silently degrade to an in-process stub.
_CRAIK_HOOK = shutil.which("craik-hook") or str(Path(sys.executable).parent / "craik-hook")

_requires_hook_binary = pytest.mark.skipif(
    not Path(_CRAIK_HOOK).exists(),
    reason="craik-hook console script not installed (editable install w/o entry points)",
)


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik")}


def _seed_home(env: dict[str, str]) -> None:
    """Create the on-disk Craik home so every thread's store handle sees schema."""
    seed = LocalStore.from_env(env)
    seed.initialize()
    seed.close()


def _invoke_real_hook_client(
    socket_path: str | None,
    *,
    vendor: str,
    timeout: str = "10",
) -> tuple[int, str]:
    """Run the REAL ``craik-hook`` console binary as a SUBPROCESS.

    This is exactly how a spawned vendor CLI invokes the hook: a separate process
    that resolves the bridge socket + vendor from its environment
    (``CRAIK_HOOK_SOCKET`` / ``CRAIK_HOOK_VENDOR``, as the gateway sets them) and
    reads the tool-request JSON on stdin. Returns ``(exit_code, stdout)`` -- the
    vendor-correct decision. ``socket_path`` ``None`` omits the socket env (the
    "no bridge configured" fail-closed case). No in-process monkeypatching of
    ``os.environ`` / ``sys.stdin`` -- the real client process owns its own.
    """
    env = dict(os.environ)
    env[VENDOR_ENV] = vendor
    env["CRAIK_HOOK_TIMEOUT"] = timeout
    if socket_path is None:
        env.pop(SOCKET_ENV, None)
    else:
        env[SOCKET_ENV] = socket_path
    completed = subprocess.run(
        [_CRAIK_HOOK],
        input=json.dumps(_TOOL_PAYLOAD),
        capture_output=True,
        text=True,
        env=env,
        timeout=float(timeout) + 10.0,
    )
    return completed.returncode, completed.stdout


def _await_approval_id(emitted: list[dict[str, object]], *, timeout: float) -> str | None:
    """Poll ``emitted`` for the bridge's surfaced ``approval.requested`` id."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for event in emitted:
            if event.get("type") == "approval.requested":
                data = event.get("data")
                if isinstance(data, dict) and isinstance(data.get("approval_id"), str):
                    return data["approval_id"]
        time.sleep(0.01)
    return None


def _record_operator_decision(
    env: dict[str, str], approval_id: str, *, decision: str
) -> None:
    """Resolve the surfaced approval exactly as the live gateway does.

    Drives the REAL operator-decide seam (``decide_approval``) on a fresh main-
    thread store handle (sqlite thread-affinity: NOT the bridge thread's handle).
    This writes the operator-attributed ``CapabilityReceipt`` AND the resolution
    the bridge's ``resolve_lookup`` reads to unblock the gate.
    """
    main_store = LocalStore.from_env(env)
    try:
        decide_approval(
            main_store,
            approval_id=approval_id,
            decision=decision,  # type: ignore[arg-type]
            operator=_OPERATOR,
            reason="e2e operator decision",
        )
    finally:
        main_store.close()


def _operator_receipts(env: dict[str, str], *, status: str) -> list[object]:
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        receipts = store.list_receipts()
    finally:
        store.close()
    return [
        r
        for r in receipts
        if r.capability == "approval.decide"
        and r.operator_subject == _OPERATOR
        and r.result.status == status
    ]


def _drive_gate(
    env: dict[str, str],
    *,
    vendor: str,
    operator_decision: str | None,
    timeout: float,
) -> dict[str, object]:
    """Run the full gated round-trip; return the observed client result.

    Opens a real ``hook_bridge_session`` (via ``gated_cli_run_session``) wired to
    a real ``LocalStore``; the gated worker calls the REAL ``craik-hook`` client
    against the live socket. The main thread services the operator decision (when
    one is given) on the real ``decide_approval`` seam while the worker blocks in
    the gate. Returns ``{"exit_code", "stdout"}`` from the client.
    """
    emitted: list[dict[str, object]] = []

    def emit(event: BackendEvent) -> None:
        emitted.append(event.as_dict())

    result: dict[str, object] = {}

    def fake_cli_run(socket_path: str) -> None:
        # The fake "vendor CLI": invoke the REAL craik-hook client exactly as the
        # spawned CLI's PreToolUse/BeforeTool hook would -- env-resolved socket +
        # vendor, tool-request JSON on stdin, vendor-correct decision out.
        exit_code, stdout = _invoke_real_hook_client(
            socket_path, vendor=vendor, timeout=str(timeout)
        )
        result["exit_code"] = exit_code
        result["stdout"] = stdout

    with gated_cli_run_session(
        run=fake_cli_run,
        store_factory=lambda: LocalStore.from_env(env, same_thread=False),
        emit=emit,
        env=env,
        vendor=vendor,
        timeout=timeout,
    ) as controller:
        if operator_decision is not None:
            approval_id = _await_approval_id(emitted, timeout=timeout)
            assert approval_id is not None, "bridge surfaced an approval request"
            _record_operator_decision(env, approval_id, decision=operator_decision)
        finished = controller.join(timeout=timeout + 5.0)
        assert finished, "gated CLI run completed (no deadlock)"

    return result


@_requires_hook_binary
def test_live_gate_approve_allows_and_records_operator_receipt(tmp_path: Path) -> None:
    """approve -> real client returns ALLOW (exit 0) + operator-attributed receipt."""
    env = _env(tmp_path)
    _seed_home(env)

    result = _drive_gate(env, vendor="anthropic", operator_decision="approved", timeout=5.0)

    # The REAL craik-hook client returned the Anthropic ALLOW: exit 0, allow JSON.
    assert result["exit_code"] == 0
    body = json.loads(str(result["stdout"]))
    assert body["hookSpecificOutput"]["permissionDecision"] == "allow"

    # The live-gating path recorded an operator-attributed CapabilityReceipt.
    passed = _operator_receipts(env, status="passed")
    assert passed, "approve-to-elevate receipt persisted with operator subject"


@_requires_hook_binary
def test_live_gate_deny_denies_and_records_denial_receipt(tmp_path: Path) -> None:
    """deny -> real client returns DENY (exit 2, deny JSON) + denial receipt."""
    env = _env(tmp_path)
    _seed_home(env)

    result = _drive_gate(env, vendor="anthropic", operator_decision="denied", timeout=5.0)

    # The REAL craik-hook client returned the Anthropic hard-block DENY: exit 2.
    assert result["exit_code"] == 2
    body = json.loads(str(result["stdout"]))
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny"

    # The denial is recorded as a denial receipt with operator attribution.
    denied = _operator_receipts(env, status="denied")
    assert denied, "denial receipt persisted with operator subject"


@_requires_hook_binary
def test_live_gate_no_decision_fails_closed(tmp_path: Path) -> None:
    """No operator decision -> the gate times out -> client returns DENY (exit 2)."""
    env = _env(tmp_path)
    _seed_home(env)

    # No operator resolution at all: the bridge decide times out -> fail-closed.
    result = _drive_gate(env, vendor="anthropic", operator_decision=None, timeout=0.3)

    assert result["exit_code"] == 2
    body = json.loads(str(result["stdout"]))
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny"


@_requires_hook_binary
def test_live_gate_unreachable_socket_fails_closed(tmp_path: Path) -> None:
    """No reachable bridge -> the REAL client fails closed (DENY), never allow.

    Points the real ``craik-hook`` binary at a socket path that has no listening
    server. The client must resolve that to a vendor-correct DENY (exit 2), never
    a silent allow -- the bedrock fail-closed guarantee.
    """
    missing_socket = str(tmp_path / "nonexistent" / "bridge.sock")
    exit_code, stdout = _invoke_real_hook_client(missing_socket, vendor="anthropic", timeout="1")
    assert exit_code == 2
    body = json.loads(stdout)
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny"


@_requires_hook_binary
def test_live_gate_no_socket_env_fails_closed() -> None:
    """No ``CRAIK_HOOK_SOCKET`` configured -> the real client denies (fail-closed)."""
    exit_code, stdout = _invoke_real_hook_client(None, vendor="anthropic", timeout="1")
    assert exit_code == 2
    body = json.loads(stdout)
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny"


@_requires_hook_binary
def test_live_gate_google_vendor_emits_gemini_dialect(tmp_path: Path) -> None:
    """A google-vendor gated run drives the client's Gemini decision dialect.

    Same real path, but ``CRAIK_HOOK_VENDOR=google`` so the client encodes the
    Gemini ``BeforeTool`` shape: approve -> ``{}`` exit 0; the gate still routes
    through the real operator decide + records the operator receipt.
    """
    env = _env(tmp_path)
    _seed_home(env)

    result = _drive_gate(env, vendor="google", operator_decision="approved", timeout=5.0)

    # Gemini allow dialect: empty object, exit 0.
    assert result["exit_code"] == 0
    assert json.loads(str(result["stdout"])) == {}
    assert _operator_receipts(env, status="passed"), "operator receipt recorded"
