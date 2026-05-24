from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pytest import MonkeyPatch

from craik.runtime.shell.external_editor import edit_text_externally


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / "home"), **extra}


def test_external_editor_round_trip_preserves_noop_content(tmp_path: Path) -> None:
    result = edit_text_externally(
        "hello",
        env=_env(tmp_path, EDITOR="true"),
        runner=lambda command: 0,
    )

    assert result.text == "hello"
    assert result.changed is False
    assert result.warning is None
    assert not list((tmp_path / "home" / "state" / "external-editor").glob("*.txt"))


def test_external_editor_reads_modified_content(tmp_path: Path) -> None:
    def _runner(command: Sequence[str]) -> int:
        Path(command[-1]).write_text("hello\nworld\n", encoding="utf-8")
        return 0

    result = edit_text_externally("hello", env=_env(tmp_path, EDITOR="cat"), runner=_runner)

    assert result.text == "hello\nworld\n"
    assert result.changed is True


def test_external_editor_failure_preserves_original_input(tmp_path: Path) -> None:
    result = edit_text_externally(
        "unchanged",
        env=_env(tmp_path, EDITOR="false"),
        runner=lambda command: 1,
    )

    assert result.text == "unchanged"
    assert result.changed is False
    assert "input unchanged" in (result.warning or "")


def test_external_editor_missing_editor_warns_when_no_fallback(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("craik.runtime.shell.external_editor.shutil.which", lambda name: None)

    result = edit_text_externally("hello", env=_env(tmp_path), runner=lambda command: 0)

    assert result.text == "hello"
    assert result.changed is False
    assert "set EDITOR or VISUAL" in (result.warning or "")
