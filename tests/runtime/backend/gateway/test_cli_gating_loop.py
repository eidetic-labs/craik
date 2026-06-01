"""Task 5.7 item B: gated CLI run does NOT deadlock against the stdin loop.

A live-gating CLI run blocks IN the hook ``decide`` (on the bridge thread) until
the operator resolves the approval -- which arrives as an ``approval.decide``
JSONL message the gateway must keep servicing WHILE the gated run is in flight.
This pins that the two loops cooperate: the gated adapter runs OFF the
stdin-reading thread, the main thread services the operator decision, the
bridge's ``resolve_lookup`` (over its OWN store handle) unblocks the hook, and
the run completes with the tool allowed -- no self-deadlock.

The "CLI subprocess" is faked in-process by a worker that forwards a tool
request to the live bridge socket (exactly as the real ``craik-hook`` client
would), so the gate path is exercised end-to-end without a real subprocess.
"""

from __future__ import annotations

import time
from pathlib import Path

from craik.runtime.backend.gateway.cli_gating_loop import gated_cli_run_session
from craik.runtime.hooks.client import _ALLOW, forward_tool_request
from craik.runtime.reviewing.approvals import decide_approval
from craik.runtime.store import LocalStore


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik")}


def test_gated_cli_run_services_approval_without_deadlock(tmp_path: Path) -> None:
    env = _env(tmp_path)
    # Seed the on-disk home so every thread's LocalStore handle sees the schema.
    seed = LocalStore.from_env(env)
    seed.initialize()
    seed.close()

    emitted: list[dict[str, object]] = []
    decision_box: dict[str, str] = {}

    def emit(event) -> None:  # noqa: ANN001
        data = event.as_dict()
        emitted.append(data)

    # The fake "CLI subprocess": forward ONE tool request to the bridge socket
    # (as the real craik-hook client does) and record the decision the bridge
    # returns. Runs on the worker thread the session starts for the gated run.
    def fake_cli_run(socket_path: str) -> None:
        decision_box["decision"] = forward_tool_request(
            socket_path,
            {"tool_name": "Bash", "tool_input": {"command": "echo hi"}},
        )

    with gated_cli_run_session(
        run=fake_cli_run,
        store_factory=lambda: LocalStore.from_env(env, same_thread=False),
        emit=emit,
        env=env,
        vendor="anthropic",
        timeout=5.0,
    ) as controller:
        # The main thread is free to service the operator decision WHILE the
        # gated worker blocks in the bridge decide. Wait for the bridge to surface
        # the approval request, then resolve it as the operator would over JSONL.
        deadline = time.monotonic() + 5.0
        approval_id = None
        while time.monotonic() < deadline:
            requested = [event for event in emitted if event["type"] == "approval.requested"]
            if requested:
                approval_id = requested[0]["data"]["approval_id"]
                break
            time.sleep(0.01)
        assert approval_id is not None, "bridge surfaced an approval request"

        # Operator approves over the MAIN thread's own store handle (sqlite
        # affinity: not the bridge thread's handle).
        main_store = LocalStore.from_env(env)
        try:
            decide_approval(
                main_store,
                approval_id=approval_id,
                decision="approved",
                operator="user:test",
                reason="ok",
            )
        finally:
            main_store.close()

        # The worker must finish (no deadlock) within the bound.
        finished = controller.join(timeout=5.0)
        assert finished, "gated CLI run completed without deadlock"

    # The operator's allow reached the gated run via the bridge resolve_lookup.
    assert decision_box["decision"] == _ALLOW


def test_gated_cli_run_timeout_denies(tmp_path: Path) -> None:
    """A gate with no operator decision fails closed (deny) and still completes."""
    env = _env(tmp_path)
    seed = LocalStore.from_env(env)
    seed.initialize()
    seed.close()

    decision_box: dict[str, str] = {}

    def fake_cli_run(socket_path: str) -> None:
        from craik.runtime.hooks.client import _DENY

        decision = forward_tool_request(
            socket_path,
            {"tool_name": "Bash", "tool_input": {"command": "echo hi"}},
        )
        decision_box["decision"] = decision
        assert decision == _DENY

    with gated_cli_run_session(
        run=fake_cli_run,
        store_factory=lambda: LocalStore.from_env(env, same_thread=False),
        emit=lambda _event: None,
        env=env,
        vendor="anthropic",
        timeout=0.2,
    ) as controller:
        # No operator decision -> the gate times out (deny) and the worker ends.
        finished = controller.join(timeout=5.0)
        assert finished

    from craik.runtime.hooks.client import _DENY

    assert decision_box["decision"] == _DENY
