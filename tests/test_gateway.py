import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from craik.cli import app
from craik.contracts.models import GatewayConfig, GatewayRuntimeState
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.gateway import (
    DEFAULT_GATEWAY_CONFIG_ID,
    DEFAULT_GATEWAY_STATE_ID,
    default_gateway_config,
    gateway_configured_state,
    gateway_failed_state,
    gateway_running_state,
    gateway_stopped_state,
    run_gateway_daemon,
)
from craik.runtime.gateway_service import (
    gateway_logs_payload,
    gateway_status_payload,
    install_gateway_service,
    request_gateway_stop,
    uninstall_gateway_service,
)
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore

NOW = datetime(2026, 5, 16, 18, 10, tzinfo=UTC)
runner = CliRunner()


def test_default_gateway_config_is_local_daemon_disabled_by_default() -> None:
    config = default_gateway_config(project_id="project_gateway", created_at=NOW)

    assert config.id == DEFAULT_GATEWAY_CONFIG_ID
    assert config.project_id == "project_gateway"
    assert config.mode == "daemon"
    assert config.bind_host == "127.0.0.1"
    assert config.pid_file == "gateway.pid"
    assert config.enabled is False


def test_gateway_lifecycle_states_preserve_policy_and_receipts() -> None:
    config = default_gateway_config(
        project_id="project_gateway",
        policy_envelope_id="policy_gateway",
        created_at=NOW,
    )

    running = gateway_running_state(
        config,
        pid=1234,
        receipt_ids=["receipt_gateway_start"],
        started_at=NOW,
    )
    stopped = gateway_stopped_state(
        running,
        receipt_ids=["receipt_gateway_stop"],
        stopped_at=NOW,
    )
    failed = gateway_failed_state(running, reason="health check failed", failed_at=NOW)

    assert running.id == DEFAULT_GATEWAY_STATE_ID
    assert running.status == "running"
    assert running.pid == 1234
    assert running.policy_envelope_id == "policy_gateway"
    assert running.receipt_ids == ["receipt_gateway_start"]
    assert stopped.status == "stopped"
    assert stopped.pid is None
    assert stopped.receipt_ids == ["receipt_gateway_stop"]
    assert failed.status == "failed"
    assert failed.pid is None
    assert "health check failed" in failed.supervision_notes


def test_gateway_configured_state_records_stopped_lifecycle() -> None:
    config = default_gateway_config(project_id="project_gateway", created_at=NOW)

    state = gateway_configured_state(config, configured_at=NOW)

    assert state.id == DEFAULT_GATEWAY_STATE_ID
    assert state.config_id == DEFAULT_GATEWAY_CONFIG_ID
    assert state.status == "stopped"
    assert state.stopped_at == NOW
    assert "configured" in state.supervision_notes[0]


def test_gateway_contracts_round_trip_through_local_store(tmp_path) -> None:
    store = LocalStore.from_paths(ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")}))
    try:
        store.initialize()
        config = default_gateway_config(project_id="project_gateway", created_at=NOW)
        state = gateway_running_state(config, pid=1234, started_at=NOW)

        store.put_gateway_config(config)
        store.put_gateway_runtime_state(state)

        assert store.get_gateway_config(config.id) == config
        assert store.get_gateway_runtime_state(state.id) == state
        assert store.list_gateway_configs() == [config]
        assert store.list_gateway_runtime_states() == [state]
    finally:
        store.close()


class _FakeGatewayServer:
    server_address = ("127.0.0.1", 8765)

    def __init__(self) -> None:
        self.closed = False
        self.shutdown_called = False

    def serve_forever(self, poll_interval: float = 0.5) -> None:
        return

    def shutdown(self) -> None:
        self.shutdown_called = True

    def server_close(self) -> None:
        self.closed = True


def test_run_gateway_daemon_persists_running_and_stopped_states(tmp_path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    server = _FakeGatewayServer()
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        config = default_gateway_config(project_id="project_gateway", created_at=NOW)
        store.put_gateway_config(config.model_copy(update={"enabled": True}))
    finally:
        store.close()

    stop_event = threading.Event()
    stop_event.set()
    stopped = run_gateway_daemon(
        paths,
        stop_event=stop_event,
        server_factory=lambda config: server,
    )

    assert stopped.status == "stopped"
    assert stopped.pid is None
    assert server.shutdown_called is True
    assert server.closed is True
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        persisted = store.get_gateway_runtime_state("gateway_state_default")
        assert persisted == stopped
    finally:
        store.close()


def test_run_gateway_daemon_rejects_existing_pid_file(tmp_path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        config = default_gateway_config(project_id="project_gateway", created_at=NOW)
        store.put_gateway_config(config.model_copy(update={"enabled": True}))
        (paths.state / "gateway.pid").write_text("1234\n")
        with pytest.raises(RuntimeError, match="pid file"):
            run_gateway_daemon(
                paths,
                stop_event=threading.Event(),
                server_factory=lambda config: _FakeGatewayServer(),
            )
    finally:
        store.close()
        (paths.state / "gateway.pid").unlink(missing_ok=True)


def test_gateway_config_rejects_public_bind_without_policy() -> None:
    with pytest.raises(ValidationError, match="public gateway bind"):
        GatewayConfig(
            id="gateway_public",
            mode="foreground",
            bind_host="0.0.0.0",
            port=8765,
            created_at=NOW,
        )


def test_gateway_state_requires_running_start_time() -> None:
    with pytest.raises(ValidationError, match="running gateway state requires"):
        GatewayRuntimeState(
            id="gateway_state",
            config_id="gateway_default",
            mode="daemon",
            status="running",
            pid=1234,
            updated_at=NOW,
        )


def test_gateway_service_install_generates_launchd_and_systemd_units(tmp_path: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        store.put_gateway_config(
            default_gateway_config(project_id="project_gateway", created_at=NOW)
        )
    finally:
        store.close()

    launchd = install_gateway_service(paths, target_platform="Darwin")
    systemd = install_gateway_service(paths, target_platform="Linux")

    assert launchd.backend == "launchd"
    assert launchd.path.name.endswith(".plist")
    assert "CRAIK_HOME" in launchd.content
    assert "craik</string><string>gateway</string><string>start" in launchd.content
    assert systemd.backend == "systemd"
    assert "ExecStart=craik gateway start" in systemd.content
    assert uninstall_gateway_service(paths)["installed"] is False


def test_gateway_status_reports_stale_pid_and_logs(tmp_path: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        config = default_gateway_config(project_id="project_gateway", created_at=NOW)
        state = gateway_running_state(config, pid=999999, started_at=NOW)
        store.put_gateway_config(config)
        store.put_gateway_runtime_state(state)
        (paths.logs / "gateway.log").write_text("one\ntwo\nthree\n", encoding="utf-8")
    finally:
        store.close()

    status = gateway_status_payload(paths)
    logs = gateway_logs_payload(paths, tail=2)

    assert status["status"] == "running"
    assert status["stale_pid"] is True
    assert logs["lines"] == ["two", "three"]


def test_gateway_stop_recovers_stale_pid_file(tmp_path: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        config = default_gateway_config(project_id="project_gateway", created_at=NOW)
        state = gateway_running_state(config, pid=999999, started_at=NOW)
        store.put_gateway_config(config)
        store.put_gateway_runtime_state(state)
        (paths.state / "gateway.pid").write_text("999999\n", encoding="utf-8")
    finally:
        store.close()

    stopped = request_gateway_stop(paths)

    assert stopped.status == "stopped"
    assert not (paths.state / "gateway.pid").exists()


def test_gateway_lifecycle_cli_commands(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    _put_operator_session(home)
    paths = ensure_craik_home(env)
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        config = default_gateway_config(project_id="project_gateway", created_at=NOW)
        store.put_gateway_config(config)
        store.put_gateway_runtime_state(gateway_configured_state(config, configured_at=NOW))
        (paths.logs / "gateway.log").write_text("gateway ready\n", encoding="utf-8")
    finally:
        store.close()

    status = runner.invoke(app, ["gateway", "status"], env=env)
    logs = runner.invoke(app, ["gateway", "logs", "--tail", "1"], env=env)
    install = runner.invoke(app, ["gateway", "install"], env=env)
    stop = runner.invoke(app, ["gateway", "stop"], env=env)
    restart = runner.invoke(app, ["gateway", "restart"], env=env)
    doctor = runner.invoke(app, ["gateway", "doctor"], env=env)

    assert status.exit_code == 0
    assert _json_payload(status)["configured"] is True
    assert logs.exit_code == 0
    assert _json_payload(logs)["lines"] == ["gateway ready"]
    assert install.exit_code == 0
    assert _json_payload(install)["installed"] is True
    assert stop.exit_code == 0
    assert _json_payload(stop)["status"] == "stopped"
    assert restart.exit_code == 0
    assert _json_payload(restart)["status"] == "restart_requested"
    assert doctor.exit_code == 0
    assert any(check["name"] == "gateway_config" for check in _json_payload(doctor)["gateway"])


def _json_payload(result) -> dict[str, object]:
    import json

    return json.loads(result.stdout)


def _put_operator_session(home: Path) -> None:
    store = OperatorSessionStore(home)
    store.put(
        OperatorSession(
            subject="operator:test",
            issuer="https://issuer.example.invalid",
            id_token_jti="jti-gateway",
            expires_at=NOW,
        )
    )
