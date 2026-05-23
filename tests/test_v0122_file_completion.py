from __future__ import annotations

from pathlib import Path

from craik.runtime.shell.textual_widgets.file_completion_popup import file_completion_candidates


def test_file_completion_filters_by_prefix(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("guide", encoding="utf-8")

    values = [candidate.token for candidate in file_completion_candidates("docs/", root=tmp_path)]

    assert values == ["@docs/guide.md"]
