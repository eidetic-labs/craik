"""Live operator approve-to-elevate orchestration for the JSONL gateway.

Phase 7.2 ③: wires the dormant Phase-5 hook-bridge machinery into the LIVE
``run_jsonl_gateway`` stdin loop. The pieces:

* :func:`gated_cli_prompt_plan` -- resolves whether a ``prompt.submit`` is a
  GATABLE CLI run with operator approval required. It returns a
  :class:`GatedCliPlan` ONLY for a CLI-surface adapter whose
  ``supports_live_gating()`` is ``True`` (so OpenAI/Codex observe-only is
  excluded) when approval is required; otherwise ``None`` (the caller falls back
  to the synchronous ``execute_prompt``).
* :class:`GatedCliPlan` -- the worker body: it sets the adapter's live-gating
  ``hook_env`` overlay and threads a ``RunContext`` whose ``decide`` is the
  operator-approval factory, then consumes ``adapter.run(ctx)``.
* :func:`run_gated_prompt` -- driven by ``jsonl.py``: runs the plan on a WORKER
  thread (via ``gateway.cli_gating_loop.gated_cli_run_session``) while the gateway
  KEEPS reading ``approval.decide`` from the shared :class:`LineSource`, so the
  operator's decision unblocks the bridge gate without deadlocking the stdin loop.

Fail-closed throughout: timeout / bridge error / resolve-lookup error / operator
deny all resolve the hook to deny so the gated CLI never executes the tool. This
module never converts that default to an allow.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from craik.runtime.backend.events import BackendEvent
from craik.runtime.backend.gateway.cli_gating_loop import gated_cli_run_session
from craik.runtime.reviewing.approval_commands import approvals_decide_result
from craik.runtime.store import LocalStore

if TYPE_CHECKING:
    from craik.runtime.backend.session import BackendPreference, PromptSource

# Gateway gated-CLI operator-decision timeout default (mirrors hook_gating's own
# default ceiling); a stuck operator/bridge fails closed before this elapses.
_DEFAULT_GATE_TIMEOUT = 300.0


@dataclass(frozen=True)
class GatedCliPlan:
    """A resolved plan to run ONE gated CLI prompt off the stdin thread.

    Built by :func:`gated_cli_prompt_plan` ONLY for a gatable CLI adapter
    (``supports_live_gating()`` True, ``surface == "cli"``) when operator
    approval is required. The JSONL gateway loop drives it via
    ``gateway.cli_gating_loop.gated_cli_run_session`` on a WORKER thread while it
    keeps servicing ``approval.decide`` -- :meth:`run` is the worker body.

    Fail-closed is owned by the bridge (timeout / error / deny -> the hook
    resolves to deny so the gated CLI never executes the tool); this plan never
    converts that default.
    """

    adapter: object
    vendor: str
    permission_mode: str | None
    require_operator_approval: bool
    env: dict[str, str] | None
    # The normalized prompt, stored alongside the adapter so ``run`` can build the
    # RunContext without re-threading it through the worker boundary.
    adapter_prompt: str = ""
    timeout: float | None = None

    def run(self, socket_path: str, emit: Callable[[BackendEvent], None]) -> None:
        """Worker body: wire the live-gating env + decide, then consume ``run``.

        Sets the adapter's ``hook_env`` to the bridge overlay (so the spawned CLI's
        pre-tool ``craik-hook`` client reaches THIS run's bridge socket) and threads
        a ``RunContext`` whose ``decide`` is the operator-approval factory over a
        per-thread store handle (sqlite affinity: the bridge thread reads the
        resolution the stdin thread writes). For CLI adapters the gate fires
        OUT-of-process via the hook bridge, so ``ctx.decide`` is belt-and-suspenders
        (the CLI ``run`` does not call it); it is wired honestly regardless so any
        in-process consult also routes to the operator. Every event the adapter
        yields is streamed via ``emit``.
        """
        from craik.runtime.backend.adapters.base import RunContext
        from craik.runtime.backend.adapters.hook_bridge import SOCKET_ENV, VENDOR_ENV
        from craik.runtime.backend.adapters.hook_gating import (
            make_operator_decide,
            make_store_resolve_lookup,
        )

        overlay = {SOCKET_ENV: socket_path, VENDOR_ENV: self.vendor}
        # The adapter is a fresh per-run instance; set the live-gating overlay so
        # the CLI subprocess env carries the bridge address.
        self.adapter.hook_env = overlay  # type: ignore[attr-defined]

        # A SEPARATE store handle for the operator-decide resolve_lookup, opened on
        # THIS worker thread (sqlite is single-thread-bound); the stdin thread
        # writes the resolution via decide_approval on its own handle.
        decide_store = LocalStore.from_env(self.env, same_thread=False)
        decide_store.initialize()
        try:
            decide = make_operator_decide(
                store=decide_store,
                emit=emit,
                timeout=self.timeout if self.timeout is not None else _DEFAULT_GATE_TIMEOUT,
                resolve_lookup=make_store_resolve_lookup(decide_store),
                permission_mode=self.permission_mode,
            )
            ctx = RunContext(
                prompt=self.adapter_prompt,
                env=self.env or {},
                emit=emit,
                decide=decide,
                require_operator_approval=self.require_operator_approval,
            )
            for event in self.adapter.run(ctx):  # type: ignore[attr-defined]
                emit(event)
        finally:
            decide_store.close()


def gated_cli_prompt_plan(
    prompt: str,
    *,
    env: dict[str, str] | None,
    source: PromptSource,
    backend: BackendPreference | str = "auto",
    require_operator_approval: bool | None = None,
) -> GatedCliPlan | None:
    """Return a :class:`GatedCliPlan` for a gatable CLI run, else ``None``.

    Engages ONLY when the resolved adapter is a CLI surface that
    ``supports_live_gating()`` (so OpenAI/Codex observe-only -- which returns
    ``False`` and raises ``LiveGatingUnsupported`` if asked to gate -- is excluded)
    AND operator approval is required. In every other case it returns ``None`` and
    the caller runs the prompt synchronously via ``execute_prompt`` (unchanged).

    A returned plan carries the active vendor ``permission_mode`` (so the TUI
    high-risk gate fires) and is driven off the stdin thread by the gateway loop;
    fail-closed remains owned by the hook bridge.
    """
    # Function-local: ``session`` imports this module's siblings; keep the import
    # here to avoid an import cycle at module load.
    from craik.runtime.backend.adapters.registry import select_adapter
    from craik.runtime.backend.session import (
        _anthropic_marker_uses_claude_code,
        _legacy_run_enabled,
        _resolve_run_identifier,
    )

    normalized_prompt = prompt.strip()
    if not normalized_prompt:
        return None
    approval_required = (
        require_operator_approval
        if require_operator_approval is not None
        else backend == "claude-code" or _anthropic_marker_uses_claude_code(env)
    )
    if not approval_required:
        return None
    if _legacy_run_enabled(env):
        # The explicit legacy fallback runs the pre-cutover synchronous path; do
        # not divert it onto the gated worker.
        return None

    identifier, _legacy_run, _legacy_provider = _resolve_run_identifier(env, backend)
    adapter = select_adapter(identifier, env, prompt_source=source)
    if getattr(adapter, "surface", None) != "cli":
        return None
    if not adapter.supports_live_gating():
        # Observe-only CLI (OpenAI/Codex): NOT gated. Returning None keeps it on
        # the synchronous path so no LiveGatingUnsupported is raised at runtime.
        return None
    return GatedCliPlan(
        adapter=adapter,
        vendor=str(getattr(adapter, "vendor", "anthropic")),
        permission_mode=_active_permission_mode(env),
        require_operator_approval=True,
        env=env,
        adapter_prompt=normalized_prompt,
    )


def _active_permission_mode(env: dict[str, str] | None) -> str | None:
    """Resolve the ACTIVE vendor's stored permission mode for the gate event.

    Reads the active vendor's ``VendorModeSpec`` (Claude / Gemini / Codex) and
    returns its STORED mode token (e.g. ``bypassPermissions`` / ``yolo`` /
    ``danger-full-access``) so the high-risk two-press gate keys off the same raw
    value. Returns ``None`` when no mode is explicitly set (no high-risk signal —
    not the display-form default, which the TUI gate wouldn't match) and on any
    resolution error -- never fail-open.
    """
    import os

    try:
        from craik.runtime.shell.contract_runtime.mode_args import active_vendor_mode_spec

        values = os.environ if env is None else env
        spec = active_vendor_mode_spec(values)
        return values.get(spec.env_var)
    except Exception:
        return None


class LineSource:
    """A single-reader, queue-backed view over the JSONL stdin stream.

    One daemon reader thread drains ``input_stream`` (a blocking ``readline``
    iterator) into a queue; :meth:`next_line` pulls from that queue. Because there
    is exactly ONE reader for the whole session, the main loop and a gated run's
    inner loop can both consume lines without two threads racing the raw stream
    for the same bytes. :meth:`next_line` with a ``timeout`` lets the gated loop
    interleave "a line arrived" with "the worker finished" -- so it never blocks
    on a readline that would otherwise prevent the worker's completion from ending
    the loop, and never busy-waits.
    """

    def __init__(self, input_stream: Any) -> None:
        import queue

        self._queue: queue.Queue[str | None] = queue.Queue()
        self._empty = queue.Empty
        self._eof = False
        self._thread = threading.Thread(
            target=self._drain, args=(input_stream,), name="craik-jsonl-stdin", daemon=True
        )
        self._thread.start()

    def _drain(self, input_stream: Any) -> None:
        try:
            for line in input_stream:
                self._queue.put(line)
        finally:
            self._queue.put(None)  # EOF sentinel

    def next_line(self, timeout: float | None = None) -> str | None:
        """Return the next line, ``None`` at EOF, or ``""`` on timeout.

        With ``timeout`` set, returns ``""`` (a benign empty line the caller skips)
        when no line arrived within the window, so a caller can poll a side
        condition between reads.
        """
        if self._eof:
            return None
        try:
            line = self._queue.get(timeout=timeout)
        except self._empty:
            return ""
        if line is None:
            self._eof = True
            return None
        return line


def handle_approval_decide(
    message: dict[str, Any],
    *,
    env: dict[str, str] | None,
    emit: Callable[[BackendEvent], None],
) -> None:
    """Resolve one operator ``approval.decide`` and emit ``approval.resolved``.

    Shared by the main stdin loop AND the gated-run inner loop so the operator's
    decision flows through the SAME ``decide_approval`` cycle in both -- recording
    the resolution (with the operator subject on the receipt) that the gated run's
    bridge ``resolve_lookup`` reads to unblock the hook.
    """
    approval_id = _required_string(message, "approval_id")
    decision = _required_string(message, "decision")
    reason = _required_string(message, "reason")
    operator = _string_or_default(message.get("operator"), "user:jsonl")
    result = approvals_decide_result(
        approval_id,
        decision=decision,
        operator=operator,
        reason=reason,
        env=env,
    )
    emit(
        BackendEvent(
            type="approval.resolved",
            data={
                "approval_id": approval_id,
                "decision": decision,
                "payload": result.payload,
            },
        )
    )


def run_gated_prompt(
    plan: GatedCliPlan,
    *,
    env: dict[str, str] | None,
    emit: Callable[[BackendEvent], None],
    source: LineSource,
) -> None:
    """Drive a gated CLI run off the stdin thread, servicing approvals in flight.

    Runs ``plan`` on a WORKER thread inside a ``hook_bridge_session`` (via
    ``gated_cli_run_session``) so this gateway thread KEEPS reading ``approval.decide``
    from the SHARED ``source`` while the gated CLI blocks in its hook. The loop
    interleaves a short-timeout read with a non-blocking ``controller.join`` so the
    worker's completion (run done, or fail-closed gate) reliably ends the loop even
    when no further operator line arrives -- no deadlock, no busy-wait.

    Fail-closed is owned by the bridge: a never-resolved gate times out to deny so
    the tool is not executed; this driver only relays approvals + joins the worker.
    """
    with gated_cli_run_session(
        run=lambda socket_path: plan.run(socket_path, emit),
        store_factory=lambda: LocalStore.from_env(env, same_thread=False),
        emit=emit,
        env=env,
        vendor=plan.vendor,
        timeout=plan.timeout,
        permission_mode=plan.permission_mode,
    ) as controller:
        while True:
            # The worker finished (run complete / fail-closed gate): stop relaying.
            if controller.join(timeout=0.0):
                break
            line = source.next_line(timeout=0.05)
            if line is None:
                # stdin exhausted: let the worker finish (bounded by the bridge
                # timeout) so a fail-closed deny still completes the run.
                controller.join(timeout=None)
                break
            stripped = line.strip()
            if not stripped:
                continue
            try:
                message = json.loads(stripped)
                if not isinstance(message, dict):
                    raise ValueError("JSONL message must be an object")
                message_type = message.get("type")
                if message_type == "approval.decide":
                    handle_approval_decide(message, env=env, emit=emit)
                elif message_type in {"session.close", "exit", "quit"}:
                    # Operator wants to stop: let the worker finish (fail-closed) so
                    # no tool runs past the close, then end.
                    controller.join(timeout=None)
                    break
                # Other message types are ignored DURING a gated run: only the
                # operator decision is load-bearing here; servicing a second
                # prompt mid-run is out of scope for the gated path.
            except Exception as error:  # noqa: BLE001 -- mirror the main loop's relay
                emit(BackendEvent(type="error", data={"message": str(error)}))


def _required_string(message: dict[str, Any], field: str) -> str:
    value = message.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{message.get('type')} requires non-empty {field}")
    return value


def _string_or_default(value: object, default: str) -> str:
    return value if isinstance(value, str) and value.strip() else default


__all__ = [
    "GatedCliPlan",
    "LineSource",
    "gated_cli_prompt_plan",
    "handle_approval_decide",
    "run_gated_prompt",
]
