"""Structured status command implementation shared by CLI and TUI surfaces."""

from __future__ import annotations

from typing import Any

from craik.runtime.contract import CommandResult, NextAction
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.policy.envelope import is_auto_approve_shape
from craik.runtime.shell.readiness import resolve_readiness
from craik.runtime.store import DATABASE_NAME, LocalStore


def status_command_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return current runtime readiness as a structured command result."""
    payload = status_payload(env)
    return CommandResult(
        payload=payload,
        shape="kv",
        next_actions=_next_actions(payload),
    )


def status_payload(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Return the status payload shared by CLI and slash dispatch."""
    report = resolve_readiness(env)
    payload = dict(report.as_dict())
    auto_approve = auto_approve_status_payload(env)
    if auto_approve is not None:
        payload["auto_approve"] = auto_approve
    return payload


def _next_actions(payload: dict[str, Any]) -> list[NextAction]:
    actions: list[NextAction] = []
    if not payload.get("operator_authenticated"):
        actions.append(
            NextAction(
                text="run /login",
                command="/login",
                field="operator_authenticated",
            )
        )
    if not payload.get("provider_configured"):
        actions.append(
            NextAction(
                text="run /auth login <provider>",
                command="/auth login",
                field="provider_configured",
            )
        )
    if not payload.get("model_configured"):
        actions.append(
            NextAction(
                text="run /model set <provider/model>",
                command="/model set",
                field="active_model",
            )
        )
    return actions


def auto_approve_status_payload(env: dict[str, str] | None) -> dict[str, Any] | None:
    """Return operator-facing auto-approve policy warning data when active."""
    for policy in _store_list(env, "list_policy_envelopes"):
        if not is_auto_approve_shape(policy):
            continue
        return {
            "active": True,
            "policy_id": getattr(policy, "id", None),
            "detail": (
                "An active policy envelope auto-approves capabilities; use a gated policy "
                "when operator review is required."
            ),
        }
    return None


def _store_list(env: dict[str, str] | None, method_name: str) -> list[Any]:
    if not _database_exists(env):
        return []
    paths = resolve_craik_paths(env)
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        method = getattr(store, method_name, None)
        if method is None:
            return []
        return list(method())
    except Exception:
        return []
    finally:
        store.close()


def _database_exists(env: dict[str, str] | None) -> bool:
    return (resolve_craik_paths(env).state / DATABASE_NAME).exists()
