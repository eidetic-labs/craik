from __future__ import annotations

from pathlib import Path


def test_slash_registry_has_no_cli_pointer_text() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "craik"
        / "runtime"
        / "shell"
        / "slash_commands.py"
    ).read_text(encoding="utf-8")

    assert "Use `craik " not in source
