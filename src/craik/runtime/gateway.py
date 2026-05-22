"""Gateway daemon lifecycle helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from craik.contracts.models import GatewayConfig, GatewayRuntimeState

DEFAULT_GATEWAY_CONFIG_ID = "gateway_default"
DEFAULT_GATEWAY_STATE_ID = "gateway_state_default"


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
