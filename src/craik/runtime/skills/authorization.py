"""Runtime authorization for governed plugin operations."""

from __future__ import annotations

from datetime import UTC, datetime

from craik.contracts.models import CapabilityTarget, PluginCapabilityGrant, PluginProbation
from craik.runtime.store import LocalStore


class PluginAuthorizationError(RuntimeError):
    """Raised when a plugin operation is not authorized by live store state."""


def authorize_plugin_operation(
    store: LocalStore,
    *,
    plugin_id: str,
    operation: str,
    target: CapabilityTarget,
    operator_identity: str,
    now: datetime | None = None,
) -> PluginCapabilityGrant:
    """Return the live grant authorizing a plugin operation, or raise."""
    checked_at = now or datetime.now(UTC)
    probation = _latest_probation(store, plugin_id)
    if probation is not None and not probation.durable_trust_granted:
        raise PluginAuthorizationError(
            "plugin operation denied: durable trust has not been granted"
        )

    for grant in _matching_grants(store, plugin_id=plugin_id, operation=operation, target=target):
        if not grant.permits_operation(operation, at=checked_at):
            continue
        if grant.approved_by and grant.approved_by != operator_identity:
            raise PluginAuthorizationError(
                "plugin operation denied: active operator does not match grant approver"
            )
        return grant
    raise PluginAuthorizationError(
        "plugin operation denied: no live capability grant permits operation"
    )


def _latest_probation(store: LocalStore, plugin_id: str) -> PluginProbation | None:
    probations = [
        probation
        for probation in store.list_plugin_probations()
        if probation.plugin_descriptor_id == plugin_id
    ]
    if not probations:
        return None
    return sorted(probations, key=lambda probation: (probation.created_at, probation.id))[-1]


def _matching_grants(
    store: LocalStore,
    *,
    plugin_id: str,
    operation: str,
    target: CapabilityTarget,
) -> list[PluginCapabilityGrant]:
    return [
        grant
        for grant in store.list_plugin_capability_grants()
        if grant.plugin_descriptor_id == plugin_id
        and operation in grant.operations
        and _target_matches(grant.target, target)
    ]


def _target_matches(granted: CapabilityTarget, requested: CapabilityTarget) -> bool:
    if granted.repo is not None and granted.repo != requested.repo:
        return False
    if granted.paths and not set(requested.paths).issubset(set(granted.paths)):
        return False
    for key, value in granted.metadata.items():
        if requested.metadata.get(key) != value:
            return False
    return True
