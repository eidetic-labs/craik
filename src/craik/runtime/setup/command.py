"""Structured setup command implementation shared by CLI and TUI surfaces."""

from __future__ import annotations

from pydantic import ValidationError

from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore
from craik.runtime.contract import CommandResult, NextAction
from craik.runtime.gateway import default_gateway_config, gateway_configured_state
from craik.runtime.paths import (
    CraikPaths,
    ensure_craik_home,
    resolve_craik_home,
    resolve_craik_paths,
)
from craik.runtime.store import DATABASE_NAME, LocalStore


class SetupOperatorSessionRequiredError(RuntimeError):
    """Raised when setup reconfiguration requires an active operator session."""


def setup_command_result(
    *,
    project_id: str | None = None,
    gateway_enabled: bool = False,
    gateway_bind_host: str = "127.0.0.1",
    gateway_port: int = 8765,
    policy_envelope_id: str | None = None,
    allow_insecure_public_gateway: bool = False,
) -> CommandResult:
    """Initialize local state and return the structured setup result."""
    resolved_paths = resolve_craik_paths()
    if (resolved_paths.state / DATABASE_NAME).exists():
        _require_operator_identity()
    public_bind = gateway_bind_host in {"0.0.0.0", "::"}  # nosec B104
    if public_bind and policy_envelope_id and not allow_insecure_public_gateway:
        raise ValueError(
            "public gateway bind without TLS requires --allow-insecure-public-gateway"
        )
    paths = ensure_craik_home()
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        config = default_gateway_config(
            project_id=project_id,
            policy_envelope_id=policy_envelope_id,
        ).model_copy(
            update={
                "bind_host": gateway_bind_host,
                "port": gateway_port,
                "enabled": gateway_enabled,
            }
        )
        try:
            config = type(config).model_validate(config.model_dump(mode="json", by_alias=True))
        except ValidationError as error:
            raise ValueError(str(error)) from None
        store.put_gateway_config(config)
        runtime_state = gateway_configured_state(config)
        store.put_gateway_runtime_state(runtime_state)
        payload = {
            "home": _paths_payload(paths),
            "gateway_config": config.model_dump(mode="json", by_alias=True),
            "gateway_runtime_state": runtime_state.model_dump(mode="json", by_alias=True),
            "secrets_written": False,
            "next_steps": [
                "Review gateway_config before enabling external ingress.",
                "Store channel secrets outside Craik config files.",
                "Run gateway diagnostics before starting the daemon.",
            ],
        }
        if public_bind:
            payload["warnings"] = [
                "Public gateway bind configured without TLS termination; place it behind TLS "
                "or keep it on a private network."
            ]
    finally:
        store.close()

    return CommandResult(
        payload=payload,
        shape="kv",
        next_actions=[
            NextAction(
                text="review gateway configuration",
                command="/gateway",
                field="gateway_config",
            ),
            NextAction(
                text="run gateway diagnostics",
                command="/doctor",
                field="gateway_runtime_state",
            ),
        ],
    )


def _paths_payload(paths: CraikPaths) -> dict[str, str]:
    return {
        "cache": str(paths.cache),
        "case_files": str(paths.case_files),
        "config": str(paths.config),
        "handoffs": str(paths.handoffs),
        "home": str(paths.home),
        "logs": str(paths.logs),
        "projects": str(paths.projects),
        "receipts": str(paths.receipts),
        "secrets": str(paths.secrets),
        "state": str(paths.state),
    }


def _require_operator_identity() -> str:
    try:
        session = OperatorSessionStore(resolve_craik_home()).get()
    except OperatorSessionNotFoundError:
        raise SetupOperatorSessionRequiredError from None
    return session.subject
