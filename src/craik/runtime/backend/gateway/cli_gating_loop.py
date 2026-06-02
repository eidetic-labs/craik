"""Off-thread gated-CLI run driver for live gating (Task 5.7 item B).

A live-gating CLI run (AnthropicCLI / GoogleCLI) blocks IN the hook ``decide``
DURING the run, waiting for the operator decision -- which arrives as an
``approval.decide`` JSONL message the gateway's stdin loop must keep servicing.
If the gated adapter ran ON the stdin-reading thread, ``decide`` would block
forever waiting for a resolution the stalled loop can never deliver
(self-deadlock, see ``hook_gating.hook_bridge_session``'s Task-5.7 note).

This module breaks the deadlock with the documented minimal-correct design: only
GATED CLI runs go off-thread; everything else stays synchronous in the gateway.
:func:`gated_cli_run_session` opens a :func:`hook_bridge_session` (whose
``resolve_lookup`` reads a SEPARATE per-bridge-thread ``LocalStore`` handle over
the same Craik home -- sqlite is single-thread-bound, so the bridge thread must
not share the stdin thread's connection), sets the bridge env overlay on the
adapter spawn, and runs the gated ``run`` callable on a WORKER thread. The
gateway's main loop keeps reading stdin and servicing ``approval.decide`` ->
``decide_approval`` (which records the resolution the bridge's ``resolve_lookup``
reads) WHILE the worker is in flight. On exit the bridge session tears down
(stops the server, joins its thread, unlinks the socket) and the worker is
joined, bounded so a wedged run never hangs gateway teardown.

The bridge ``decide`` already fails closed (hook timeout / teardown / error ->
deny); this driver never converts that default.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from craik.runtime.backend.adapters.hook_gating import hook_bridge_session

if TYPE_CHECKING:
    from craik.runtime.backend.events import BackendEvent
    from craik.runtime.store import LocalStore

# Bound the worker join on teardown so a wedged gated run never hangs the gateway.
_WORKER_JOIN_SECONDS = 5.0


class GatedRunController:
    """Handle to the worker thread running a gated CLI adapter off the stdin loop.

    The gateway keeps servicing ``approval.decide`` on its main thread and polls
    :meth:`join` (or :meth:`is_alive`) to learn when the gated run finishes. Any
    exception raised inside the worker is re-surfaced from :meth:`join` so a real
    run() failure is NOT silently swallowed.
    """

    def __init__(self, thread: threading.Thread, error_box: dict[str, Exception]) -> None:
        self._thread = thread
        self._error_box = error_box

    def is_alive(self) -> bool:
        """Whether the gated worker is still running."""
        return self._thread.is_alive()

    def join(self, timeout: float | None = None) -> bool:
        """Join the worker; return True if it finished, re-raising its error.

        Returns ``False`` if the worker is still alive after ``timeout`` (the
        caller keeps servicing approvals). A worker exception is re-raised here so
        it is never swallowed.
        """
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            return False
        error = self._error_box.get("error")
        if error is not None:
            raise error
        return True


@contextmanager
def gated_cli_run_session(
    *,
    run: Callable[[str], None],
    store_factory: Callable[[], LocalStore],
    emit: Callable[[BackendEvent], None],
    env: dict[str, str] | None,
    vendor: str,
    timeout: float | None = None,
    permission_mode: str | None = None,
) -> Iterator[GatedRunController]:
    """Run a gated CLI ``run`` OFF the stdin thread inside a live hook bridge.

    Opens a :func:`hook_bridge_session` whose ``resolve_lookup`` reads a SEPARATE
    ``LocalStore`` handle (``store_factory()`` -- opened + closed ON the bridge
    thread, respecting sqlite thread-affinity), then starts a daemon WORKER
    thread that invokes ``run(socket_path)`` -- the gated adapter spawn, given the
    bridge socket so its pre-tool ``craik-hook`` client reaches the bridge. The
    yielded :class:`GatedRunController` lets the caller's main loop service
    ``approval.decide`` while the worker blocks in the gate. On exit the worker is
    joined (bounded) and the bridge session tears down (stop server, join thread,
    unlink socket). The bridge ``decide`` is fail-closed (timeout/teardown/error
    -> deny); this driver never converts that default.

    ``run`` receives the bridge socket path. ``store_factory`` MUST return a fresh
    store handle each call (the bridge thread owns its own connection). ``emit`` is
    the gateway event sink the bridge uses to surface ``approval.requested``.
    ``permission_mode`` is the ACTIVE vendor permission mode carried onto each
    ``approval.requested`` (so the TUI high-risk two-press gate fires); ``None``
    leaves it off the event.
    """
    bridge_store = store_factory()
    bridge_store.initialize()

    session_kwargs: dict[str, Any] = {
        "store": bridge_store,
        "emit": emit,
        "env": env,
        "vendor": vendor,
        "permission_mode": permission_mode,
    }
    if timeout is not None:
        session_kwargs["timeout"] = timeout

    error_box: dict[str, Exception] = {}

    try:
        with hook_bridge_session(**session_kwargs) as (socket_path, _overlay):

            def _worker() -> None:
                try:
                    run(socket_path)
                except Exception as error:  # noqa: BLE001 -- re-raised in join()
                    # Captured, not swallowed: GatedRunController.join() re-raises
                    # it on the gateway thread so a real run() failure surfaces.
                    # KeyboardInterrupt/SystemExit deliberately propagate (worker
                    # ends; bounded join + bridge teardown fail-closed the hook).
                    error_box["error"] = error

            worker = threading.Thread(target=_worker, name="craik-gated-cli-run", daemon=True)
            worker.start()
            controller = GatedRunController(worker, error_box)
            try:
                yield controller
            finally:
                # Bound the join so a wedged gated run never hangs teardown; the
                # daemon thread + the bridge teardown (socket dropped on context
                # exit) guarantee the hook resolves to a fail-closed deny.
                worker.join(timeout=_WORKER_JOIN_SECONDS)
    finally:
        bridge_store.close()


__all__ = ["GatedRunController", "gated_cli_run_session"]
