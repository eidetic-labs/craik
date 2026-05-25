from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

from craik.runtime.shell.textual_app import CraikApp
from craik.runtime.shell.textual_widgets.text_selection_hint import SELECTION_HINT_MESSAGE

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_text_selection_wiring.py"
spec = importlib.util.spec_from_file_location("check_text_selection_wiring", SCRIPT)
assert spec is not None
check_text_selection_wiring = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(check_text_selection_wiring)


def test_text_selection_hint_matches_wired_behavior() -> None:
    assert "click and drag" in SELECTION_HINT_MESSAGE
    assert "copy shortcut" in SELECTION_HINT_MESSAGE
    assert "Option" not in SELECTION_HINT_MESSAGE
    assert "Ctrl+Shift in Linux" not in SELECTION_HINT_MESSAGE


def test_transcript_widget_allows_text_selection() -> None:
    async def run() -> None:
        app = CraikApp(env={"CRAIK_TUI_SELECTION_HINT": "0"})
        async with app.run_test() as pilot:
            transcript = pilot.app.query_one("#transcript")
            assert pilot.app.ALLOW_SELECT is True
            assert transcript.allow_select is True

    asyncio.run(run())


def test_text_selection_wiring_guard_passes_current_tree() -> None:
    assert check_text_selection_wiring.text_selection_failures() == []


def test_text_selection_wiring_guard_rejects_stale_hint(tmp_path: Path) -> None:
    root = _minimal_tree(tmp_path)
    hint = (
        root
        / "src"
        / "craik"
        / "runtime"
        / "shell"
        / "textual_widgets"
        / "text_selection_hint.py"
    )
    hint.write_text(
        'SELECTION_HINT_MESSAGE = "hold Option while dragging on macOS"\n',
        encoding="utf-8",
    )

    failures = check_text_selection_wiring.text_selection_failures(root)

    assert any("stale selection hint" in failure for failure in failures)


def test_text_selection_wiring_guard_requires_theme_selection_rule(tmp_path: Path) -> None:
    root = _minimal_tree(tmp_path)
    theme = root / "src" / "craik" / "runtime" / "shell" / "textual_app_dark.tcss"
    theme.write_text("Screen { background: $background; }\n", encoding="utf-8")

    failures = check_text_selection_wiring.text_selection_failures(root)

    assert any(
        "textual_app_dark.tcss: missing Screen > .screen--selection" in failure
        for failure in failures
    )


def _minimal_tree(tmp_path: Path) -> Path:
    root = tmp_path
    shell = root / "src" / "craik" / "runtime" / "shell"
    widgets = shell / "textual_widgets"
    widgets.mkdir(parents=True)
    (shell / "textual_app.py").write_text(
        """
class CraikApp:
    ALLOW_SELECT = True

    def compose(self):
        yield RichLog(id="transcript", markup=True, wrap=True)
""",
        encoding="utf-8",
    )
    (widgets / "text_selection_hint.py").write_text(
        (
            'SELECTION_HINT_MESSAGE = "click and drag in the transcript, '
            'then use your copy shortcut"\n'
        ),
        encoding="utf-8",
    )
    selection_rule = (
        "Screen > .screen--selection {\n"
        "    background: #B4ACE6;\n"
        "    color: #101010;\n"
        "}\n"
    )
    (shell / "textual_app_dark.tcss").write_text(selection_rule, encoding="utf-8")
    (shell / "textual_app_light.tcss").write_text(selection_rule, encoding="utf-8")
    return root
