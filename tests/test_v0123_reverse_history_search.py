from __future__ import annotations

from pathlib import Path

from craik.runtime.shell.shell_history import append_history
from craik.runtime.shell.textual_widgets.history_search import HistorySearchOverlay


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / "home")}


def test_reverse_history_search_filters_newest_first(tmp_path: Path) -> None:
    env = _env(tmp_path)
    append_history("first prompt", env=env)
    append_history("second prompt", env=env)
    append_history("second prompt", env=env)
    overlay = HistorySearchOverlay(env=env)

    overlay.open(initial_query="second")

    assert overlay.display is True
    assert overlay.matches == ["second prompt"]
    selected = overlay.selected()
    assert selected is not None
    assert selected.text == "second prompt"


def test_reverse_history_search_navigation_and_selection(tmp_path: Path) -> None:
    env = _env(tmp_path)
    append_history("alpha", env=env)
    append_history("beta", env=env)
    overlay = HistorySearchOverlay(env=env)

    overlay.open()
    overlay.move(1)
    selected = overlay.selected(submit=True)

    assert selected is not None
    assert selected.text == "alpha"
    assert selected.submit is True


def test_reverse_history_search_dismisses_without_selection(tmp_path: Path) -> None:
    overlay = HistorySearchOverlay(env=_env(tmp_path))

    overlay.open()
    overlay.dismiss()

    assert overlay.display is False


def test_reverse_history_search_empty_history_is_graceful(tmp_path: Path) -> None:
    overlay = HistorySearchOverlay(env=_env(tmp_path))

    overlay.open(initial_query="missing")

    assert overlay.matches == []
    assert overlay.selected() is None


def test_reverse_history_search_cycles_scope(tmp_path: Path) -> None:
    overlay = HistorySearchOverlay(env=_env(tmp_path))

    assert overlay.cycle_scope() == "project"
    assert overlay.cycle_scope() == "all"
    assert overlay.cycle_scope() == "session"
