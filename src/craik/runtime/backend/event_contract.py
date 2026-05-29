"""Gateway event contract validation shared by Python backend emitters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

from craik.runtime.backend.events import BackendEvent

CONTRACT_RESOURCE = "gateway_event_contract.json"


@dataclass(frozen=True)
class GatewayEventContractIssue:
    """One validation issue for a normalized Gateway event."""

    event_index: int
    event_type: str
    message: str


@cache
def gateway_event_contract() -> dict[str, Any]:
    """Return the machine-readable Gateway event contract."""
    contract_text = (
        resources.files("craik.runtime.backend").joinpath(CONTRACT_RESOURCE).read_text()
    )
    contract = json.loads(contract_text)
    if not isinstance(contract, dict):
        raise TypeError("Gateway event contract must be a JSON object")
    return contract


def known_event_types() -> set[str]:
    """Return event names defined by the Gateway event contract."""
    return set(_event_rules())


def validate_gateway_event(
    event: BackendEvent | dict[str, Any],
    *,
    event_index: int = 0,
) -> list[GatewayEventContractIssue]:
    """Return contract issues for one Gateway event payload."""
    payload = event.as_dict() if isinstance(event, BackendEvent) else event
    event_rules = _event_rules()
    event_type = payload.get("type")
    event_type_text = event_type if isinstance(event_type, str) else "<missing>"
    issues: list[GatewayEventContractIssue] = []

    rule = event_rules.get(event_type_text)
    if rule is None:
        issues.append(
            GatewayEventContractIssue(
                event_index,
                event_type_text,
                f"unsupported event type `{event_type_text}`",
            )
        )
        return issues

    data = payload.get("data")
    if not isinstance(data, dict):
        issues.append(
            GatewayEventContractIssue(
                event_index,
                event_type_text,
                "event data must be a JSON object",
            )
        )
        return issues

    for requirement in _requirements_for(rule):
        _validate_requirement(
            issues,
            event_index=event_index,
            event_type=event_type_text,
            payload=payload,
            requirement=requirement,
        )

    return issues


def validate_gateway_events(
    events: list[BackendEvent | dict[str, Any]],
) -> list[GatewayEventContractIssue]:
    """Return contract issues for a sequence of Gateway events."""
    return [
        issue
        for index, event in enumerate(events)
        for issue in validate_gateway_event(event, event_index=index)
    ]


def format_gateway_event_contract_issues(
    issues: list[GatewayEventContractIssue],
) -> str:
    """Render contract issues for logs, errors, and tests."""
    return "; ".join(
        f"event {issue.event_index} `{issue.event_type}`: {issue.message}"
        for issue in issues
    )


def _event_rules() -> dict[str, Any]:
    event_types = gateway_event_contract().get("event_types")
    if not isinstance(event_types, dict):
        raise TypeError("Gateway event contract must define event_types")
    return event_types


def _requirements_for(rule: object) -> list[dict[str, Any]]:
    if not isinstance(rule, dict):
        return []
    requirements = rule.get("requirements", [])
    if not isinstance(requirements, list):
        raise TypeError("Gateway event contract requirements must be arrays")
    return [requirement for requirement in requirements if isinstance(requirement, dict)]


def _validate_requirement(
    issues: list[GatewayEventContractIssue],
    *,
    event_index: int,
    event_type: str,
    payload: dict[str, Any],
    requirement: dict[str, Any],
) -> None:
    kind = requirement.get("kind")
    message = requirement.get("message")
    if not isinstance(message, str) or not message:
        raise TypeError("Gateway event contract requirement missing message")

    if kind in {"non_empty_string", "array"}:
        path = requirement.get("path")
        if not isinstance(path, str) or not path:
            raise TypeError("Gateway event contract requirement missing path")
        value = _value_at(payload, path)
        failed = (
            not isinstance(value, str) or not value.strip()
            if kind == "non_empty_string"
            else not isinstance(value, list)
        )
        if failed:
            issues.append(GatewayEventContractIssue(event_index, event_type, message))
        return

    if kind in {"one_non_empty_string", "one_present"}:
        paths = requirement.get("paths")
        if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
            raise TypeError("Gateway event contract multi-path requirement missing paths")
        if kind == "one_non_empty_string":
            passed = any(
                isinstance(value := _value_at(payload, path), str) and value.strip()
                for path in paths
            )
        else:
            passed = any(_path_exists(payload, path) for path in paths)
        if not passed:
            issues.append(GatewayEventContractIssue(event_index, event_type, message))
        return

    raise ValueError(f"unsupported Gateway event contract requirement kind: {kind}")


def _value_at(payload: dict[str, Any], path: str) -> object:
    value: object = payload
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def _path_exists(payload: dict[str, Any], path: str) -> bool:
    value: object = payload
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return False
        value = value[key]
    return True
