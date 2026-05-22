"""Gateway daemon lifecycle helpers."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol

from craik.contracts.models import GatewayConfig, GatewayRuntimeState
from craik.runtime.paths import CraikPaths
from craik.runtime.store import LocalStore

DEFAULT_GATEWAY_CONFIG_ID = "gateway_default"
DEFAULT_GATEWAY_STATE_ID = "gateway_state_default"


class GatewayDaemonError(RuntimeError):
    """Base gateway daemon runtime error."""


class GatewayDaemonAlreadyRunningError(GatewayDaemonError):
    """Raised when the gateway pid-file lock already exists."""


class GatewayDaemonConfigError(GatewayDaemonError):
    """Raised when the gateway cannot load a persisted configuration."""


class GatewayServer(Protocol):
    server_address: tuple[str | bytes | bytearray, int]

    def serve_forever(self, poll_interval: float = 0.5) -> None:
        raise NotImplementedError

    def shutdown(self) -> None:
        raise NotImplementedError

    def server_close(self) -> None:
        raise NotImplementedError


ServerFactory = Callable[[GatewayConfig], GatewayServer]


def default_gateway_config(
    *,
    project_id: str | None = None,
    policy_envelope_id: str | None = None,
    created_at: datetime | None = None,
) -> GatewayConfig:
    """Build the default local-only gateway configuration."""
    now = created_at or datetime.now(UTC)
    return GatewayConfig(
        id=DEFAULT_GATEWAY_CONFIG_ID,
        project_id=project_id,
        mode="daemon",
        bind_host="127.0.0.1",
        port=8765,
        pid_file="gateway.pid",
        log_file="gateway.log",
        policy_envelope_id=policy_envelope_id,
        enabled=False,
        created_at=now,
    )


def gateway_starting_state(
    config: GatewayConfig,
    *,
    pid: int | None = None,
    receipt_ids: list[str] | None = None,
    updated_at: datetime | None = None,
) -> GatewayRuntimeState:
    """Create a persisted starting state before launching gateway work."""
    now = updated_at or datetime.now(UTC)
    return GatewayRuntimeState(
        id=DEFAULT_GATEWAY_STATE_ID,
        config_id=config.id,
        project_id=config.project_id,
        mode=config.mode,
        status="starting",
        pid=pid,
        updated_at=now,
        policy_envelope_id=config.policy_envelope_id,
        receipt_ids=receipt_ids or [],
        supervision_notes=["Gateway start requested; ingress remains policy-bound."],
    )


def gateway_configured_state(
    config: GatewayConfig,
    *,
    receipt_ids: list[str] | None = None,
    configured_at: datetime | None = None,
) -> GatewayRuntimeState:
    """Create an initial stopped state after gateway configuration is written."""
    now = configured_at or datetime.now(UTC)
    return GatewayRuntimeState(
        id=DEFAULT_GATEWAY_STATE_ID,
        config_id=config.id,
        project_id=config.project_id,
        mode=config.mode,
        status="stopped",
        pid=None,
        stopped_at=now,
        updated_at=now,
        policy_envelope_id=config.policy_envelope_id,
        receipt_ids=receipt_ids or [],
        supervision_notes=["Gateway configured; daemon has not been started."],
    )


def gateway_running_state(
    config: GatewayConfig,
    *,
    pid: int,
    receipt_ids: list[str] | None = None,
    started_at: datetime | None = None,
) -> GatewayRuntimeState:
    """Create a running gateway state after process launch succeeds."""
    now = started_at or datetime.now(UTC)
    return GatewayRuntimeState(
        id=DEFAULT_GATEWAY_STATE_ID,
        config_id=config.id,
        project_id=config.project_id,
        mode=config.mode,
        status="running",
        pid=pid,
        started_at=now,
        updated_at=now,
        policy_envelope_id=config.policy_envelope_id,
        receipt_ids=receipt_ids or [],
        supervision_notes=["Gateway process is marked running by the supervisor."],
    )


def gateway_stopped_state(
    state: GatewayRuntimeState,
    *,
    receipt_ids: list[str] | None = None,
    stopped_at: datetime | None = None,
) -> GatewayRuntimeState:
    """Create a stopped state while preserving gateway lifecycle links."""
    now = stopped_at or datetime.now(UTC)
    return state.model_copy(
        update={
            "status": "stopped",
            "pid": None,
            "stopped_at": now,
            "updated_at": now,
            "receipt_ids": receipt_ids if receipt_ids is not None else state.receipt_ids,
            "supervision_notes": [
                *state.supervision_notes,
                "Gateway stop requested; process is no longer active.",
            ],
        }
    )


def gateway_failed_state(
    state: GatewayRuntimeState,
    *,
    reason: str,
    failed_at: datetime | None = None,
) -> GatewayRuntimeState:
    """Create a failed state with an explicit supervisor reason."""
    now = failed_at or datetime.now(UTC)
    return state.model_copy(
        update={
            "status": "failed",
            "pid": None,
            "updated_at": now,
            "supervision_notes": [*state.supervision_notes, reason],
        }
    )


def run_gateway_daemon(
    paths: CraikPaths,
    *,
    stop_event: threading.Event | None = None,
    ready_event: threading.Event | None = None,
    server_factory: ServerFactory | None = None,
) -> GatewayRuntimeState:
    """Run the foreground gateway service and persist lifecycle transitions."""
    store = LocalStore.from_paths(paths)
    lock_path: Path | None = None
    server: GatewayServer | None = None
    state: GatewayRuntimeState | None = None
    interrupted = False
    try:
        store.initialize()
        config = store.get_gateway_config(DEFAULT_GATEWAY_CONFIG_ID)
        if config is None:
            raise GatewayDaemonConfigError(
                "gateway configuration missing; run craik setup before starting the daemon"
            )
        if not config.enabled:
            raise GatewayDaemonConfigError(
                "gateway configuration is disabled; run craik setup --enable-gateway"
            )
        lock_path = _gateway_pid_path(paths, config)
        _acquire_gateway_lock(lock_path)
        state = gateway_starting_state(config, pid=os.getpid())
        store.put_gateway_runtime_state(state)
        try:
            server = (server_factory or _http_server)(config)
            state = gateway_running_state(config, pid=os.getpid())
            store.put_gateway_runtime_state(state)
            if ready_event is not None:
                ready_event.set()
            if stop_event is not None:
                while not stop_event.wait(0.1):
                    pass
            else:
                server.serve_forever()
        except KeyboardInterrupt:
            interrupted = True
        except Exception as error:
            failed = gateway_failed_state(
                state,
                reason=f"gateway daemon failed: {error}",
            )
            store.put_gateway_runtime_state(failed)
            raise
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
        stopped = gateway_stopped_state(state)
        if interrupted:
            stopped = stopped.model_copy(
                update={
                    "supervision_notes": [
                        *stopped.supervision_notes,
                        "Gateway stopped after keyboard interrupt.",
                    ],
                }
            )
        store.put_gateway_runtime_state(stopped)
        return stopped
    finally:
        if lock_path is not None:
            _release_gateway_lock(lock_path)
        store.close()


def _gateway_pid_path(paths: CraikPaths, config: GatewayConfig) -> Path:
    pid_file = config.pid_file or "gateway.pid"
    path = Path(pid_file)
    if not path.is_absolute():
        path = paths.state / path
    return path


def _acquire_gateway_lock(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        raise GatewayDaemonAlreadyRunningError(
            f"gateway daemon already running or stale pid file exists: {path}"
        ) from None
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(f"{os.getpid()}\n")


def _release_gateway_lock(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _http_server(config: GatewayConfig) -> GatewayServer:
    return ThreadingHTTPServer((config.bind_host, config.port), _GatewayRequestHandler)


class _GatewayRequestHandler(BaseHTTPRequestHandler):
    server_version = "CraikGateway/0.8"

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = json.dumps(
            {
                "status": "ok",
                "service": "craik.gateway",
            },
            sort_keys=True,
        ).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return
