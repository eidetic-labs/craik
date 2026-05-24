"""Policy-envelope inspection helpers."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

from craik.contracts.models import PolicyEnvelope

_WILDCARDS = {"*", "all", "capability:*", "craik:*"}
_AUTO_VALUES = {"auto", "auto_approve", "auto-approve", "allow", "allowed"}


def is_auto_approve_shape(policy: PolicyEnvelope | object) -> bool:
    """Return whether a policy envelope effectively auto-approves every capability.

    Precedence (high-to-low):
    1. ``approve_all_capabilities=True`` is the master switch and returns
       ``True`` even when ``required_approval_capabilities`` is non-empty.
    2. Wildcards in ``allowlist`` or ``allowed_capabilities`` auto-approve.
    3. Per-capability gates auto-approve only when every gate is auto-shaped.
    """
    if _truthy_value(_field(policy, "approve_all_capabilities")):
        return True
    if _approval_required(policy):
        return False
    if _allows_wildcard(_field(policy, "allowlist")):
        return True
    if _allows_wildcard(_field(policy, "allowed_capabilities")):
        return True
    gates = _field(policy, "per_capability_gates")
    return _all_gates_auto(gates)


def _field(policy: object, name: str) -> Any:
    if isinstance(policy, Mapping):
        return policy.get(name)
    value = getattr(policy, name, None)
    if value is not None:
        return value
    metadata = getattr(policy, "metadata", None)
    if isinstance(metadata, Mapping):
        return metadata.get(name)
    return None


def _truthy_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _approval_required(policy: object) -> bool:
    value = _field(policy, "required_approval_capabilities")
    if value is None:
        value = _field(policy, "approval_required")
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def _allows_wildcard(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in _WILDCARDS
    if isinstance(value, Mapping):
        raw_values = [*value.keys(), *value.values()]
    elif isinstance(value, Collection):
        raw_values = list(value)
    else:
        return False
    return any(isinstance(item, str) and item.strip().lower() in _WILDCARDS for item in raw_values)


def _all_gates_auto(value: Any) -> bool:
    if not isinstance(value, Mapping) or not value:
        return False
    for gate in value.values():
        if isinstance(gate, Mapping):
            gate_value = gate.get("mode") or gate.get("decision") or gate.get("gate")
        else:
            gate_value = gate
        if not isinstance(gate_value, str) or gate_value.strip().lower() not in _AUTO_VALUES:
            return False
    return True
