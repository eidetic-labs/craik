from __future__ import annotations

import stat
from pathlib import Path

from craik.runtime.shell.shell_history import (
    append_history,
    history_path,
    read_history,
    search_history,
)


def _env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik"), **overrides}


def test_history_uses_global_file_in_single_operator_mode(tmp_path: Path) -> None:
    env = _env(tmp_path)

    append_history("/help", env=env)

    path = history_path(env)
    assert path.name == "shell-history.jsonl"
    assert [entry.text for entry in read_history(env=env)] == ["/help"]
    if path.exists():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_history_uses_anonymous_file_when_audited_without_session(tmp_path: Path) -> None:
    env = _env(tmp_path, CRAIK_OPERATOR_REQUIRED="1")

    append_history("hello", env=env)

    assert history_path(env).name == "shell-history-anonymous.jsonl"


def test_history_can_be_disabled(tmp_path: Path) -> None:
    env = _env(tmp_path, CRAIK_HISTORY_MAX_ENTRIES="0")

    append_history("hello", env=env)

    assert not history_path(env).exists()


def test_history_rotates_and_searches_newest_first(tmp_path: Path) -> None:
    env = _env(tmp_path, CRAIK_HISTORY_MAX_ENTRIES="2")

    append_history("alpha", env=env)
    append_history("beta", env=env)
    append_history("alpha", env=env)

    assert [entry.text for entry in read_history(env=env)] == ["beta", "alpha"]
    assert search_history("a", env=env) == ["alpha"]
