"""Enforce OAuth loopback, state, PKCE, and refresh-token safety invariants."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH_SOURCES = ROOT / "src" / "craik" / "runtime" / "auth" / "sources"
OAUTH_FILES = [
    ROOT / "src" / "craik" / "runtime" / "auth" / "oauth_loopback.py",
    *[
        path
        for path in sorted(AUTH_SOURCES.glob("*_oauth.py"))
        if path.name != "local_cli_oauth.py"
    ],
]
LOOPBACK_HOST = "127.0.0.1"
PERSISTENCE_CALLS = {"write", "write_text", "write_bytes", "set_password"}


def main() -> int:
    failures: list[str] = []
    for path in OAUTH_FILES:
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = OAuthSafetyVisitor(path)
        visitor.visit(tree)
        failures.extend(visitor.failures)

    if failures:
        print("OAuth callback safety checks failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("OAuth callback safety checks passed.")
    return 0


class OAuthSafetyVisitor(ast.NodeVisitor):
    """AST visitor for OAuth safety-sensitive code."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.failures: list[str] = []
        self._class_depth = 0
        self._function_depth = 0

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_depth += 1
        for statement in node.body:
            if isinstance(statement, ast.Assign | ast.AnnAssign):
                self._check_refresh_token_attribute(statement)
        self.generic_visit(node)
        self._class_depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function_depth += 1
        self.generic_visit(node)
        self._function_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function_depth += 1
        self.generic_visit(node)
        self._function_depth -= 1

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._class_depth == 0 and self._function_depth == 0:
            self._check_refresh_token_attribute(node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self._class_depth == 0 and self._function_depth == 0:
            self._check_refresh_token_attribute(node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node.func)
        if name == "HTTPServer":
            self._check_http_server_bind(node)
        elif name.endswith(".bind"):
            self._check_socket_bind(node)
        elif name.endswith("uvicorn.run") or name == "uvicorn.run":
            self._check_uvicorn_host(node)
        if _call_leaf_name(node.func) in PERSISTENCE_CALLS and _contains_pkce_verifier(node):
            self._fail(node, "PKCE verifier must not be passed to persistence APIs")
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if any(isinstance(op, ast.Eq | ast.NotEq) for op in node.ops) and _mentions_state(node):
            self._fail(node, "OAuth state comparisons must use hmac.compare_digest")
        self.generic_visit(node)

    def _check_http_server_bind(self, node: ast.Call) -> None:
        if not node.args:
            self._fail(node, "HTTPServer bind address must be explicit")
            return
        if not _tuple_first_string_is(node.args[0], LOOPBACK_HOST):
            self._fail(node, "HTTPServer must bind to literal 127.0.0.1")

    def _check_socket_bind(self, node: ast.Call) -> None:
        if not node.args or not _tuple_first_string_is(node.args[0], LOOPBACK_HOST):
            self._fail(node, "socket.bind must bind to literal 127.0.0.1")

    def _check_uvicorn_host(self, node: ast.Call) -> None:
        for keyword in node.keywords:
            if keyword.arg == "host":
                if not _string_is(keyword.value, LOOPBACK_HOST):
                    self._fail(node, "uvicorn.run host must be literal 127.0.0.1")
                return
        self._fail(node, "uvicorn.run host must be explicit")

    def _check_refresh_token_attribute(self, node: ast.Assign | ast.AnnAssign) -> None:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            name = _target_name(target)
            if name and "refresh_token" in name and not name.endswith("_handle"):
                self._fail(node, "refresh tokens must not be stored in module/class attributes")

    def _fail(self, node: ast.AST, message: str) -> None:
        location = f"{_display_path(self.path)}:{getattr(node, 'lineno', 1)}"
        self.failures.append(f"{location}: {message}")


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _call_leaf_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _target_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _tuple_first_string_is(node: ast.AST, expected: str) -> bool:
    return (
        isinstance(node, ast.Tuple)
        and bool(node.elts)
        and _string_is(node.elts[0], expected)
    )


def _string_is(node: ast.AST, expected: str) -> bool:
    return isinstance(node, ast.Constant) and node.value == expected


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


def _contains_pkce_verifier(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and "verifier" in child.id.lower():
            return True
        if isinstance(child, ast.Attribute) and "verifier" in child.attr.lower():
            return True
    return False


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
