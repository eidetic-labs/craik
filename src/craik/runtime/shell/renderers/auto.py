"""Payload shape detection for renderer dispatch."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from craik.runtime.contract.command_result import PayloadShape


def detect_shape(payload: Any) -> PayloadShape:
    """Infer the best renderer shape for a structured payload."""
    if isinstance(payload, str):
        return "markdown" if _looks_like_markdown(payload) else "kv"
    if isinstance(payload, list):
        return _list_shape(payload)
    if isinstance(payload, Mapping):
        return _mapping_shape(payload)
    return "kv"


def _mapping_shape(payload: Mapping[Any, Any]) -> PayloadShape:
    if not payload:
        return "kv"
    nested_count = sum(1 for value in payload.values() if isinstance(value, dict | list))
    if nested_count == 0:
        return "kv"
    if nested_count <= 2:
        return "card"
    return "tree"


def _list_shape(payload: list[Any]) -> PayloadShape:
    if not payload:
        return "table"
    if all(isinstance(item, Mapping) for item in payload):
        if any(
            any(isinstance(value, dict | list) for value in item.values())
            for item in payload
            if isinstance(item, Mapping)
        ):
            return "card_list"
        return "table"
    return "card_list"


def _looks_like_markdown(value: str) -> bool:
    stripped = value.lstrip()
    return stripped.startswith(("#", "-", "*", ">")) or "\n" in value
