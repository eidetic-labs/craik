from __future__ import annotations

import pytest

from craik.cli_errors import craik_error_handler


def test_craik_error_handler_suppresses_traceback_by_default(capsys, monkeypatch) -> None:
    monkeypatch.delenv("CRAIK_DEBUG", raising=False)

    with pytest.raises(SystemExit) as raised:
        craik_error_handler(RuntimeError, RuntimeError("boom"), None)

    captured = capsys.readouterr()
    assert raised.value.code == 2
    assert "Internal error: RuntimeError: boom" in captured.err
    assert "Run with CRAIK_DEBUG=1" in captured.err
    assert "Traceback" not in captured.err
