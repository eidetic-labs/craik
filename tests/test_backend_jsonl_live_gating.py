"""Phase 7.2 ③: live operator approve-to-elevate through the JSONL gateway loop.

The dormant Phase-5 hook-bridge machinery (``gated_cli_run_session`` +
``make_operator_decide`` + ``make_store_resolve_lookup``) is now wired into the
LIVE ``run_jsonl_gateway`` stdin loop: for a GATABLE CLI adapter when operator
approval is required, a ``prompt.submit`` launches the gated CLI run on a WORKER
thread inside a ``hook_bridge_session``, and the stdin loop KEEPS READING so the
operator's ``approval.decide`` message lands and unblocks the gate. Approve =
authorize this tool call outside the static policy (approve-to-elevate); deny /
timeout = fail-closed block.

These E2E tests drive the real ``run_jsonl_gateway`` with:

* a fake gatable CLI adapter whose ``run`` forwards ONE tool request to the live
  bridge socket (exactly as the real ``craik-hook`` client would), so the gate
  round-trips end-to-end without a real subprocess; and
* a stdin stream that is FED the operator's ``approval.decide`` message WHILE the
  gated worker is in flight (a background thread watches stdout for
  ``approval.requested`` and writes the decision back), proving the stdin loop
  interleaves with the worker (no deadlock / no busy-wait).
"""

from __future__ import annotations

import io
import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from craik.runtime.backend import jsonl as jsonl_backend
from craik.runtime.backend import session as session_backend
from craik.runtime.backend.adapters.base import RunContext
from craik.runtime.backend.events import BackendEvent, tool_event
from craik.runtime.backend.jsonl import run_jsonl_gateway
from craik.runtime.hooks.client import _ALLOW, _DENY, forward_tool_request
from craik.runtime.store import LocalStore


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik")}


def _seed_home(env: dict[str, str]) -> None:
    seed = LocalStore.from_env(env)
    seed.initialize()
    seed.close()


_TOOL_PAYLOAD = {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}


class _FakeGatableCLI:
    """A gatable CLI adapter whose ``run`` forwards one tool request to the bridge.

    Mirrors a real ``AnthropicCLI``/``GoogleCLI``: ``supports_live_gating()`` is
    ``True``, ``surface == "cli"``, it carries a ``hook_env`` overlay set by the
    gateway, and its ``run`` reaches the bridge over the socket the overlay names
    (the real CLI does this out-of-process via the ``craik-hook`` PreToolUse
    hook). It records the bridge decision and only yields a ``tool.used`` event
    when the operator ALLOWED -- so the test can assert the tool proceeded.
    """

    vendor = "anthropic"
    surface = "cli"

    last_decision: dict[str, str] = {}

    def __init__(self, original_env: dict[str, str] | None = None) -> None:
        self.original_env = original_env
        self.hook_env: dict[str, str] | None = None
        self.last_payload: dict[str, object] | None = None

    def supports_live_gating(self) -> bool:
        return True

    def auth_source(self) -> str:
        return "fake-cli"

    def run(self, ctx: RunContext) -> Any:
        # The hook overlay must have been set by the gateway BEFORE run().
        assert self.hook_env is not None, "gateway must set hook_env on the gated path"
        from craik.runtime.backend.adapters.hook_bridge import SOCKET_ENV

        socket_path = self.hook_env[SOCKET_ENV]
        decision = forward_tool_request(socket_path, dict(_TOOL_PAYLOAD), timeout=10.0)
        _FakeGatableCLI.last_decision["decision"] = decision
        self.last_payload = {"run": {"id": "run_fake"}, "task": {"id": "task_fake"}}
        if decision == _ALLOW:
            # Tool PROCEEDS: surface a tool.used event the test can observe.
            yield tool_event(tool="Bash", source="anthropic-cli", command="echo hi")
        # On deny nothing executes (no tool.used); the gate already blocked it.


def _drive_gateway_with_operator(
    env: dict[str, str],
    *,
    prompt_message: dict[str, object],
    operator_decision: str | None,
) -> list[dict[str, object]]:
    """Run ``run_jsonl_gateway`` feeding an operator decision mid-flight.

    ``stdin`` delivers ``prompt_message`` first, then BLOCKS until a watcher
    thread observes the ``approval.requested`` on stdout and (if
    ``operator_decision`` is not ``None``) appends the matching ``approval.decide``
    line, then a ``session.close``. This proves the stdin loop services the
    operator decision WHILE the gated worker is in flight.
    """
    outbuf = _LineCapture()
    instream = _ScriptedStdin()
    instream.feed(json.dumps(prompt_message))

    stop = threading.Event()

    def watcher() -> None:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and not stop.is_set():
            approval_id = outbuf.find_approval_id()
            if approval_id is not None:
                if operator_decision is not None:
                    instream.feed(
                        json.dumps(
                            {
                                "type": "approval.decide",
                                "approval_id": approval_id,
                                "decision": operator_decision,
                                "reason": "operator decision",
                            }
                        )
                    )
                instream.feed(json.dumps({"type": "session.close"}))
                instream.close()
                return
            time.sleep(0.01)
        # No approval surfaced (e.g. timeout path): close so the loop can end.
        instream.feed(json.dumps({"type": "session.close"}))
        instream.close()

    watch = threading.Thread(target=watcher, name="operator-watcher", daemon=True)
    watch.start()
    try:
        run_jsonl_gateway(env=env, stdin=instream, stdout=outbuf)
    finally:
        stop.set()
        watch.join(timeout=5.0)
    return outbuf.events()


class _LineCapture:
    """A thread-safe stdout sink that also lets a watcher scan emitted events."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buf = io.StringIO()

    def write(self, text: str) -> int:
        with self._lock:
            return self._buf.write(text)

    def flush(self) -> None:
        with self._lock:
            self._buf.flush()

    def events(self) -> list[dict[str, object]]:
        with self._lock:
            raw = self._buf.getvalue()
        return [json.loads(line) for line in raw.splitlines() if line.strip()]

    def find_approval_id(self) -> str | None:
        for event in self.events():
            if event.get("type") == "approval.requested":
                data = event.get("data")
                if isinstance(data, dict) and isinstance(data.get("approval_id"), str):
                    return data["approval_id"]
        return None


class _ScriptedStdin:
    """A blocking line iterator a watcher thread can append lines to mid-run."""

    def __init__(self) -> None:
        self._lock = threading.Condition()
        self._lines: list[str] = []
        self._closed = False

    def feed(self, line: str) -> None:
        with self._lock:
            self._lines.append(line + "\n")
            self._lock.notify_all()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._lock.notify_all()

    def __iter__(self) -> _ScriptedStdin:
        return self

    def __next__(self) -> str:
        with self._lock:
            while not self._lines and not self._closed:
                self._lock.wait(timeout=10.0)
            if self._lines:
                return self._lines.pop(0)
            raise StopIteration


@pytest.fixture
def _gated_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, str]:
    """Route ``prompt.submit`` through the gated CLI path with the fake adapter."""
    env = _env(tmp_path)
    _seed_home(env)
    _FakeGatableCLI.last_decision = {}

    # Force the gated-CLI plan: the prompt run resolves to the fake gatable CLI
    # adapter with operator approval required. The store handle the bridge uses is
    # the on-disk home opened cross-thread (sqlite affinity), matching production.
    def fake_plan(prompt: str, *, env: dict[str, str] | None, source: str):  # noqa: ANN202
        return session_backend.GatedCliPlan(
            adapter=_FakeGatableCLI(original_env=env),
            vendor="anthropic",
            permission_mode="bypassPermissions",
            require_operator_approval=True,
            env=env,
        )

    monkeypatch.setattr(session_backend, "gated_cli_prompt_plan", fake_plan)
    monkeypatch.setattr(jsonl_backend, "gated_cli_prompt_plan", fake_plan)
    return env


def test_gated_prompt_approve_proceeds_and_records_operator_receipt(
    _gated_cli: dict[str, str],
) -> None:
    env = _gated_cli
    events = _drive_gateway_with_operator(
        env,
        prompt_message={"type": "prompt.submit", "text": "do a thing"},
        operator_decision="approved",
    )

    # The bridge surfaced the approval request to the operator...
    requested = [e for e in events if e["type"] == "approval.requested"]
    assert requested, "operator approval was surfaced"
    # ...carrying the active vendor permission_mode so the TUI high-risk gate fires.
    assert requested[0]["data"]["permission_mode"] == "bypassPermissions"
    # The operator's approve reached the gated run via the bridge.
    assert _FakeGatableCLI.last_decision["decision"] == _ALLOW
    # The tool PROCEEDED (approve-to-elevate): the tool.used event was emitted.
    assert any(e["type"] == "tool.used" for e in events)
    # The gateway resolved the approval.
    resolved = [e for e in events if e["type"] == "approval.resolved"]
    assert any(e["data"]["decision"] == "approved" for e in resolved)

    # The elevation receipt is persisted WITH operator attribution.
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        receipts = store.list_receipts()
    finally:
        store.close()
    operator_receipts = [
        r
        for r in receipts
        if r.capability == "approval.decide"
        and r.operator_subject == "user:jsonl"
        and r.result.status == "passed"
    ]
    assert operator_receipts, "approve-to-elevate receipt persisted with operator subject"


def test_gated_prompt_deny_blocks_tool(_gated_cli: dict[str, str]) -> None:
    env = _gated_cli
    events = _drive_gateway_with_operator(
        env,
        prompt_message={"type": "prompt.submit", "text": "do a thing"},
        operator_decision="denied",
    )

    assert any(e["type"] == "approval.requested" for e in events)
    # The operator's deny reached the gated run; the tool did NOT proceed.
    assert _FakeGatableCLI.last_decision["decision"] == _DENY
    assert not any(e["type"] == "tool.used" for e in events)
    # The denial is recorded.
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        receipts = store.list_receipts()
    finally:
        store.close()
    assert any(
        r.capability == "approval.decide" and r.result.status == "denied" for r in receipts
    )


def test_gated_prompt_timeout_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env = _env(tmp_path)
    _seed_home(env)
    _FakeGatableCLI.last_decision = {}

    def fake_plan(prompt: str, *, env: dict[str, str] | None, source: str):  # noqa: ANN202
        return session_backend.GatedCliPlan(
            adapter=_FakeGatableCLI(original_env=env),
            vendor="anthropic",
            permission_mode="default",
            require_operator_approval=True,
            env=env,
            # A tiny gate timeout so a never-resolved request fails closed fast.
            timeout=0.2,
        )

    monkeypatch.setattr(session_backend, "gated_cli_prompt_plan", fake_plan)
    monkeypatch.setattr(jsonl_backend, "gated_cli_prompt_plan", fake_plan)

    # No operator decision at all -> the gate times out -> fail-closed deny.
    events = _drive_gateway_with_operator(
        env,
        prompt_message={"type": "prompt.submit", "text": "do a thing"},
        operator_decision=None,
    )

    assert any(e["type"] == "approval.requested" for e in events)
    assert _FakeGatableCLI.last_decision["decision"] == _DENY
    assert not any(e["type"] == "tool.used" for e in events)


def test_non_gated_prompt_runs_synchronously(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A normal (non-gated) run still executes synchronously via execute_prompt."""
    env = _env(tmp_path)
    _seed_home(env)

    # No gated plan: the jsonl loop falls back to the synchronous execute_prompt.
    monkeypatch.setattr(
        session_backend,
        "gated_cli_prompt_plan",
        lambda prompt, *, env, source: None,
    )
    monkeypatch.setattr(
        jsonl_backend,
        "gated_cli_prompt_plan",
        lambda prompt, *, env, source: None,
    )

    calls: dict[str, object] = {}

    def fake_execute_prompt(prompt: str, *, env=None, source="tui", stream=None, **kwargs):  # noqa: ANN001, ANN202
        calls["prompt"] = prompt
        calls["source"] = source
        if stream is not None:
            stream(BackendEvent(type="run.event", data={"message": "sync run"}))
        return session_backend.BackendPromptResult(payload={}, events=[])

    monkeypatch.setattr(jsonl_backend, "execute_prompt", fake_execute_prompt)

    instream = io.StringIO(
        json.dumps({"type": "prompt.submit", "text": "hello"})
        + "\n"
        + json.dumps({"type": "session.close"})
        + "\n"
    )
    outbuf = io.StringIO()
    run_jsonl_gateway(env=env, stdin=instream, stdout=outbuf)

    assert calls["prompt"] == "hello"
    assert calls["source"] == "jsonl"
    events = [json.loads(line) for line in outbuf.getvalue().splitlines() if line.strip()]
    assert any(e["type"] == "run.event" for e in events)


def test_observe_only_adapter_is_not_gated(tmp_path: Path) -> None:
    """An observe-only adapter (supports_live_gating() False) is NOT gated.

    ``gated_cli_prompt_plan`` must return ``None`` for an adapter that does not
    support live gating (OpenAI/Codex CLI), so the synchronous path runs and no
    ``LiveGatingUnsupported`` is raised at runtime.
    """
    from craik.runtime.backend.adapters.openai_cli import OpenAICLI

    adapter = OpenAICLI()
    assert adapter.supports_live_gating() is False

    env = _env(tmp_path)
    # Even with approval required, an observe-only CLI yields no gated plan.
    plan = session_backend.gated_cli_prompt_plan(
        "prompt",
        env=env,
        source="jsonl",
        backend="openai-cli",
    )
    assert plan is None


def test_active_permission_mode_returns_stored_token_or_none(tmp_path: Path) -> None:
    # The high-risk gate keys off the RAW stored mode token for the ACTIVE vendor.
    # Pin the active vendor to anthropic in an isolated CRAIK_HOME so resolution
    # does not depend on ambient ~/.craik state (CI has none and would otherwise
    # default to provider_openai, reading the WRONG vendor's env var).
    from craik.runtime.backend.gateway.gated_prompt import _active_permission_mode
    from craik.runtime.modeling.settings import ModelSettings, ModelSettingsStore

    env = _env(tmp_path)
    ModelSettingsStore.from_env(env).save(ModelSettings(active_model="anthropic/claude-sonnet-4"))

    # Unset -> None (NOT a display-form default the TUI gate wouldn't match) so the
    # two-press confirm only fires for an explicitly-chosen mode.
    assert _active_permission_mode(env) is None
    assert (
        _active_permission_mode({**env, "CRAIK_CLAUDE_PERMISSION_MODE": "bypassPermissions"})
        == "bypassPermissions"
    )
