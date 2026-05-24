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


def test_dock_snapshot_guard_rejects_comment_only_region_y_reference(
    tmp_path: Path,
) -> None:
    _write_default_css_widget(tmp_path, "CommentOnlyBottom")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_comment_only.py").write_text(
        textwrap.dedent(
            """
            # CommentOnlyBottom region.y would be tested here eventually.
            def test_comment_only() -> None:
                assert True
            """
        ),
        encoding="utf-8",
    )

    assert check_dock_bottom_snapshot_coverage.missing_snapshot_coverage(tmp_path) == [
        "CommentOnlyBottom"
    ]


def test_dock_snapshot_guard_rejects_region_y_outside_assert(tmp_path: Path) -> None:
    _write_default_css_widget(tmp_path, "AssignmentOnlyBottom")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_assignment_only.py").write_text(
        textwrap.dedent(
            """
            def test_assignment_only() -> None:
                y = AssignmentOnlyBottom.region.y
                assert y >= 0
            """
        ),
        encoding="utf-8",
    )

    assert check_dock_bottom_snapshot_coverage.missing_snapshot_coverage(tmp_path) == [
        "AssignmentOnlyBottom"
    ]


def test_dock_snapshot_guard_accepts_query_one_binding_region_y_assert(
    tmp_path: Path,
) -> None:
    _write_default_css_widget(tmp_path, "BoundBottom")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_bound.py").write_text(
        textwrap.dedent(
            """
            def test_bound(pilot) -> None:
                widget = pilot.app.query_one(BoundBottom)
                assert widget.region.y > 0
            """
        ),
        encoding="utf-8",
    )

    assert check_dock_bottom_snapshot_coverage.missing_snapshot_coverage(tmp_path) == []


def test_dock_snapshot_guard_scans_all_theme_tcss_variants(tmp_path: Path) -> None:
    shell_dir = tmp_path / "src" / "craik" / "runtime" / "shell"
    shell_dir.mkdir(parents=True)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (shell_dir / "textual_app.py").write_text(
        'def compose(self):\n    yield LightOnlyBottom(id="light-only")\n',
        encoding="utf-8",
    )
    (shell_dir / "textual_app_dark.tcss").write_text("", encoding="utf-8")
    (shell_dir / "textual_app_light.tcss").write_text(
        "#light-only {\n    dock: bottom;\n}\n",
        encoding="utf-8",
    )
    (tests_dir / "test_unrelated.py").write_text("def test_unrelated(): assert True\n")

    assert check_dock_bottom_snapshot_coverage.bottom_docked_widgets(tmp_path) == {
        "LightOnlyBottom"
    }
    assert check_dock_bottom_snapshot_coverage.missing_snapshot_coverage(tmp_path) == [
        "LightOnlyBottom"
    ]


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


def _write_default_css_widget(root: Path, class_name: str) -> None:
    widget_dir = root / "src" / "craik" / "runtime" / "shell" / "textual_widgets"
    widget_dir.mkdir(parents=True, exist_ok=True)
    (widget_dir / f"{class_name.lower()}.py").write_text(
        textwrap.dedent(
            f'''
            class {class_name}:
                DEFAULT_CSS = """
                {class_name} {{
                    dock: bottom;
                }}
                """
            '''
        ),
        encoding="utf-8",
    )
