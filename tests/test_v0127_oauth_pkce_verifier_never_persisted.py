from __future__ import annotations

import ast
from pathlib import Path

PERSISTENCE_METHODS = {"write", "write_text", "write_bytes", "set_password"}


def test_pkce_verifier_is_not_passed_to_persistence_apis() -> None:
    failures: list[str] = []
    for path in _oauth_source_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _call_leaf_name(node.func) not in PERSISTENCE_METHODS:
                continue
            if _contains_pkce_verifier(node):
                failures.append(f"{path.relative_to(_repo_root())}:{node.lineno}")

    assert failures == []


def test_pkce_verifier_is_sent_only_to_token_exchange_payloads() -> None:
    source_names = set()
    for path in _oauth_source_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key in node.keys:
                    if isinstance(key, ast.Constant) and key.value == "code_verifier":
                        source_names.add(path.name)

    assert {"openai_oauth.py", "anthropic_oauth.py"} <= source_names


def _contains_pkce_verifier(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and "verifier" in child.id.lower():
            return True
        if isinstance(child, ast.Attribute) and "verifier" in child.attr.lower():
            return True
    return False


def _call_leaf_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _oauth_source_paths() -> list[Path]:
    root = _repo_root()
    auth_sources = root / "src/craik/runtime/auth/sources"
    return [
        root / "src/craik/runtime/auth/oauth_loopback.py",
        *[
            path
            for path in sorted(auth_sources.glob("*_oauth.py"))
            if path.name != "local_cli_oauth.py"
        ],
    ]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
