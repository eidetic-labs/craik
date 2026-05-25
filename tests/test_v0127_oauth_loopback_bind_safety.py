from __future__ import annotations

import ast
from pathlib import Path

import pytest

from craik.runtime.auth.oauth_loopback import (
    LOOPBACK_HOST,
    OAuthLoopbackError,
    validate_loopback_host,
)


def test_loopback_host_constant_is_literal_ipv4_loopback() -> None:
    assert LOOPBACK_HOST == "127.0.0.1"


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "::1", "localhost", "10.0.0.1"])
def test_loopback_host_validation_rejects_non_literal_127001(host: str) -> None:
    with pytest.raises(OAuthLoopbackError, match="127.0.0.1"):
        validate_loopback_host(host)


def test_loopback_listener_http_server_binds_literal_127001() -> None:
    tree = ast.parse(_oauth_loopback_path().read_text(encoding="utf-8"))
    binds = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "HTTPServer"
    ]

    assert binds, "OAuth loopback listener must construct an HTTPServer"
    assert all(_binds_literal_loopback(call) for call in binds)


def _binds_literal_loopback(call: ast.Call) -> bool:
    if not call.args or not isinstance(call.args[0], ast.Tuple):
        return False
    host = call.args[0].elts[0] if call.args[0].elts else None
    return isinstance(host, ast.Constant) and host.value == "127.0.0.1"


def _oauth_loopback_path() -> Path:
    return Path(__file__).resolve().parents[1] / "src/craik/runtime/auth/oauth_loopback.py"
