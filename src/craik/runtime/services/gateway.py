"""Gateway service installation, status, and stop helpers."""

from __future__ import annotations

import os
import platform
import signal
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from craik.contracts.models import GatewayConfig, GatewayRuntimeState
from craik.runtime.gateway import (
    DEFAULT_GATEWAY_CONFIG_ID,
    DEFAULT_GATEWAY_STATE_ID,
    GatewayDaemonConfigError,
    _gateway_pid_path,
    _release_gateway_lock,
    gateway_configured_state,
    gateway_stopped_state,
)
from craik.runtime.paths import CraikPaths
from craik.runtime.store import LocalStore


@dataclass(frozen=True)
class GatewayServiceInstall:
    """Generated gateway service installation metadata."""

    backend: str
    path: Path
    installed: bool
    content: str
    notes: tuple[str, ...]


def gateway_stopping_state(
    state: GatewayRuntimeState,
    *,
    updated_at: datetime | None = None,
) -> GatewayRuntimeState:
    """Create a stopping state while preserving process metadata."""
    now = updated_at or datetime.now(UTC)
    return state.model_copy(
        update={
            "status": "stopping",
            "updated_at": now,
            "supervision_notes": [
                *state.supervision_notes,
                "Gateway stop requested by operator.",
            ],
        }
    )


def gateway_status_payload(paths: CraikPaths) -> dict[str, object]:
    """Return gateway service/config/runtime status without starting work."""
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        config = store.get_gateway_config(DEFAULT_GATEWAY_CONFIG_ID)
        state = store.get_gateway_runtime_state(DEFAULT_GATEWAY_STATE_ID)
    finally:
        store.close()
    pid_path = _gateway_pid_path(paths, config) if config else paths.state / "gateway.pid"
    stale_pid = False
    if state and state.pid and state.status in {"running", "starting", "stopping"}:
        stale_pid = not _pid_exists(state.pid)
    return {
        "configured": config is not None,
        "enabled": bool(config.enabled) if config else False,
        "status": state.status if state else "not configured",
        "pid": state.pid if state else None,
        "pid_file": str(pid_path),
        "pid_file_exists": pid_path.exists(),
        "stale_pid": stale_pid,
        "bind": f"{config.bind_host}:{config.port}" if config else None,
        "log_file": _gateway_log_path(paths, config).as_posix() if config else None,
    }


def install_gateway_service(
    paths: CraikPaths,
    *,
    target_platform: str | None = None,
) -> GatewayServiceInstall:
    """Generate and write a user-service definition for the gateway."""
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        config = store.get_gateway_config(DEFAULT_GATEWAY_CONFIG_ID)
    finally:
        store.close()
    if config is None:
        raise GatewayDaemonConfigError("gateway configuration missing; run craik setup first")
    backend = _service_backend(target_platform or platform.system())
    service_dir = paths.config / "services"
    service_dir.mkdir(parents=True, exist_ok=True)
    if backend == "launchd":
        path = service_dir / "com.eidetic-labs.craik.gateway.plist"
        content = _launchd_plist(paths, config)
        notes = ("Copy to ~/Library/LaunchAgents and run launchctl bootstrap gui/$UID.",)
    elif backend == "systemd":
        path = service_dir / "craik-gateway.service"
        content = _systemd_unit(paths, config)
        notes = ("Copy to ~/.config/systemd/user and run systemctl --user enable --now.",)
    else:
        path = service_dir / "craik-gateway.windows.txt"
        content = _windows_service_plan(paths, config)
        notes = ("Windows service installation is documented as a manual plan for this release.",)
    path.write_text(content, encoding="utf-8")
    return GatewayServiceInstall(backend, path, True, content, notes)


def uninstall_gateway_service(paths: CraikPaths) -> dict[str, object]:
    """Remove generated gateway service definitions from Craik config."""
    service_dir = paths.config / "services"
    removed: list[str] = []
    for name in (
        "com.eidetic-labs.craik.gateway.plist",
        "craik-gateway.service",
        "craik-gateway.windows.txt",
    ):
        path = service_dir / name
        if path.exists():
            path.unlink()
            removed.append(str(path))
    return {"removed": removed, "installed": False}


def request_gateway_stop(
    paths: CraikPaths,
    *,
    signal_process: bool = False,
) -> GatewayRuntimeState:
    """Persist a gateway stop request and recover stale pid state."""
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        config = store.get_gateway_config(DEFAULT_GATEWAY_CONFIG_ID)
        state = store.get_gateway_runtime_state(DEFAULT_GATEWAY_STATE_ID)
        if config is None:
            raise GatewayDaemonConfigError("gateway configuration missing; run craik setup first")
        if state is None:
            state = gateway_configured_state(config)
        if state.pid and _pid_exists(state.pid) and signal_process:
            os.kill(state.pid, signal.SIGTERM)
        stopping = gateway_stopping_state(state)
        stopped = gateway_stopped_state(stopping)
        store.put_gateway_runtime_state(stopped)
        pid_path = _gateway_pid_path(paths, config)
        if pid_path.exists() and (not state.pid or not _pid_exists(state.pid) or signal_process):
            _release_gateway_lock(pid_path)
        return stopped
    finally:
        store.close()


def gateway_logs_payload(paths: CraikPaths, *, tail: int = 50) -> dict[str, object]:
    """Return recent gateway log lines without failing if logs are absent."""
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        config = store.get_gateway_config(DEFAULT_GATEWAY_CONFIG_ID)
    finally:
        store.close()
    log_path = _gateway_log_path(paths, config)
    if not log_path.exists():
        return {"log_file": str(log_path), "exists": False, "lines": []}
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"log_file": str(log_path), "exists": True, "lines": lines[-tail:]}


def _gateway_log_path(paths: CraikPaths, config: GatewayConfig | None) -> Path:
    log_file = config.log_file if config and config.log_file else "gateway.log"
    path = Path(log_file)
    if not path.is_absolute():
        path = paths.logs / path
    return path


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _service_backend(system_name: str) -> str:
    lowered = system_name.lower()
    if lowered == "darwin":
        return "launchd"
    if lowered == "linux":
        return "systemd"
    return "windows-plan"


def _launchd_plist(paths: CraikPaths, config: GatewayConfig) -> str:
    log_path = _gateway_log_path(paths, config)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.eidetic-labs.craik.gateway</string>
  <key>ProgramArguments</key>
  <array><string>craik</string><string>gateway</string><string>start</string></array>
  <key>EnvironmentVariables</key>
  <dict><key>CRAIK_HOME</key><string>{paths.home}</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{log_path}</string>
  <key>StandardErrorPath</key><string>{log_path}</string>
  <key>WorkingDirectory</key><string>{paths.home}</string>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
"""


def _systemd_unit(paths: CraikPaths, config: GatewayConfig) -> str:
    log_path = _gateway_log_path(paths, config)
    return f"""[Unit]
Description=Craik gateway service
After=network.target

[Service]
Type=simple
Environment=CRAIK_HOME={paths.home}
ExecStart=craik gateway start
Restart=on-failure
StandardOutput=append:{log_path}
StandardError=append:{log_path}
WorkingDirectory={paths.home}

[Install]
WantedBy=default.target
"""


def _windows_service_plan(paths: CraikPaths, config: GatewayConfig) -> str:
    log_path = _gateway_log_path(paths, config)
    return (
        "Windows service installation is manual in v0.11.0.\n"
        f"CRAIK_HOME={paths.home}\n"
        "Command=craik gateway start\n"
        f"LogFile={log_path}\n"
    )
