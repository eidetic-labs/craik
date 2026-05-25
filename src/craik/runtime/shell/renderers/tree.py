"""Compact tree renderer."""

from __future__ import annotations

from typing import Any

from rich.markup import escape
from rich.tree import Tree

from craik.runtime.shell.renderers.status_icons import icon_for_bool, icon_for_status


def render_tree(payload: Any, *, empty_state_message: str | None = None) -> Tree:
    """Render a nested payload as a compact Rich tree."""
    tree = Tree("result")
    if payload in ({}, [], None):
        tree.add(escape(empty_state_message or "No values."))
        return tree
    _add_value(tree, payload)
    return tree


def _add_value(node: Tree, value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            label = escape(str(key).replace("_", " "))
            if _is_scalar(child):
                node.add(f"{label}: {_scalar(child)}")
            else:
                branch = node.add(label)
                _add_value(branch, child)
        return
    if isinstance(value, list):
        for index, child in enumerate(value, start=1):
            label = f"[{index}]"
            if _is_scalar(child):
                node.add(f"{label}: {_scalar(child)}")
            else:
                branch = node.add(label)
                _add_value(branch, child)
        return
    node.add(_scalar(value))


def _is_scalar(value: Any) -> bool:
    return not isinstance(value, dict | list)


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return icon_for_bool(value)
    if value is None:
        return icon_for_status("missing")
    return escape(str(value))
