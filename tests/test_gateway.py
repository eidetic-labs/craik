from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from craik.contracts.models import GatewayConfig, GatewayRuntimeState
from craik.runtime.gateway import (
    DEFAULT_GATEWAY_CONFIG_ID,
    DEFAULT_GATEWAY_STATE_ID,
    default_gateway_config,
    gateway_configured_state,
    gateway_failed_state,
    gateway_running_state,
    gateway_stopped_state,
)
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore

NOW = datetime(2026, 5, 16, 18, 10, tzinfo=UTC)


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
