from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_dock_bottom_snapshot_coverage.py"
_SPEC = importlib.util.spec_from_file_location("check_dock_bottom_snapshot_coverage", _SCRIPT)
assert _SPEC is not None
assert _SPEC.loader is not None
check_dock_bottom_snapshot_coverage = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_dock_bottom_snapshot_coverage)


def test_dock_snapshot_guard_detects_uncovered_bottom_widget(tmp_path: Path) -> None:
    widget_dir = tmp_path / "src" / "craik" / "runtime" / "shell" / "textual_widgets"
    widget_dir.mkdir(parents=True)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (widget_dir / "missing.py").write_text(
        textwrap.dedent(
            '''
            class MissingBottom:
                DEFAULT_CSS = """
                MissingBottom {
                    dock: bottom;
                }
                """
            '''
        ),
        encoding="utf-8",
    )
    (tests_dir / "test_unrelated.py").write_text("def test_unrelated(): assert True\n")

    assert check_dock_bottom_snapshot_coverage.missing_snapshot_coverage(tmp_path) == [
        "MissingBottom"
    ]


def test_dock_snapshot_guard_accepts_region_y_coverage(tmp_path: Path) -> None:
    widget_dir = tmp_path / "src" / "craik" / "runtime" / "shell" / "textual_widgets"
    widget_dir.mkdir(parents=True)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (widget_dir / "covered.py").write_text(
        textwrap.dedent(
            '''
            class CoveredBottom:
                DEFAULT_CSS = """
                CoveredBottom {
                    dock: bottom;
                }
                """
            '''
        ),
        encoding="utf-8",
    )
    (tests_dir / "test_covered.py").write_text(
        "def test_covered(widget): assert CoveredBottom.region.y > 0\n",
        encoding="utf-8",
    )

    assert check_dock_bottom_snapshot_coverage.missing_snapshot_coverage(tmp_path) == []


def test_dock_snapshot_guard_covers_current_bottom_stack() -> None:
    widgets = check_dock_bottom_snapshot_coverage.bottom_docked_widgets()

    assert {
        "FooterSafeArea",
        "StatusBar",
        "AccentEmission",
        "CraikInput",
        "ToastQueue",
        "WorkingIndicator",
    }.issubset(widgets)
    assert check_dock_bottom_snapshot_coverage.missing_snapshot_coverage() == []
