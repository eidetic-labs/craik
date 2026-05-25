from __future__ import annotations

import ast
from pathlib import Path


def test_oauth_loopback_state_validation_uses_compare_digest() -> None:
    source = _oauth_loopback_source()
    tree = ast.parse(source)

    compare_digest_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "compare_digest"
        and any(_mentions_state(argument) for argument in node.args)
    ]

    assert compare_digest_calls, "OAuth state validation must use hmac.compare_digest"


def test_oauth_loopback_does_not_use_direct_state_equality() -> None:
    tree = ast.parse(_oauth_loopback_source())
    direct_state_comparisons = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and any(isinstance(op, ast.Eq | ast.NotEq) for op in node.ops)
        and _mentions_state(node)
    ]

    assert direct_state_comparisons == []


def _mentions_state(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and "state" in child.id.lower():
            return True
        if isinstance(child, ast.Attribute) and "state" in child.attr.lower():
            return True
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            if "state" in child.value.lower():
                return True
    return False


def _oauth_loopback_source() -> str:
    path = Path(__file__).resolve().parents[1] / "src/craik/runtime/auth/oauth_loopback.py"
    return path.read_text(encoding="utf-8")
