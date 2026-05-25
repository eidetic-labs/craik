"""Validate terminal text-selection wiring for the canonical TUI."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXTUAL_APP = ROOT / "src" / "craik" / "runtime" / "shell" / "textual_app.py"
TEXT_SELECTION_HINT = (
    ROOT
    / "src"
    / "craik"
    / "runtime"
    / "shell"
    / "textual_widgets"
    / "text_selection_hint.py"
)
THEMES = (
    ROOT / "src" / "craik" / "runtime" / "shell" / "textual_app_dark.tcss",
    ROOT / "src" / "craik" / "runtime" / "shell" / "textual_app_light.tcss",
)
STALE_HINT_TERMS = ("hold Option", "Ctrl+Shift in Linux", "Shift while dragging")


def main() -> int:
    failures = text_selection_failures()
    if failures:
        print("Text-selection wiring checks failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Text-selection wiring checks passed.")
    return 0


def text_selection_failures(root: Path = ROOT) -> list[str]:
    """Return text-selection wiring failures for a Craik checkout."""
    textual_app = root / "src" / "craik" / "runtime" / "shell" / "textual_app.py"
    hint = (
        root
        / "src"
        / "craik"
        / "runtime"
        / "shell"
        / "textual_widgets"
        / "text_selection_hint.py"
    )
    themes = (
        root / "src" / "craik" / "runtime" / "shell" / "textual_app_dark.tcss",
        root / "src" / "craik" / "runtime" / "shell" / "textual_app_light.tcss",
    )
    failures: list[str] = []
    failures.extend(_textual_app_failures(textual_app))
    failures.extend(_hint_failures(hint))
    for theme in themes:
        failures.extend(_theme_failures(theme))
    return failures


def _textual_app_failures(path: Path) -> list[str]:
    if not path.exists():
        return [f"{_display_path(path)}: missing textual app"]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "CraikApp":
            allow_select = _class_constant(node, "ALLOW_SELECT")
            if allow_select is not True:
                return [
                    "src/craik/runtime/shell/textual_app.py: "
                    "CraikApp.ALLOW_SELECT must be True"
                ]
            if not _compose_mounts_transcript_richlog(node):
                return [
                    "src/craik/runtime/shell/textual_app.py: compose() must mount "
                    "RichLog(id='transcript')"
                ]
            return []
    return ["src/craik/runtime/shell/textual_app.py: missing CraikApp"]


def _class_constant(node: ast.ClassDef, name: str) -> object:
    for child in node.body:
        if isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(child.value)
    return None


def _compose_mounts_transcript_richlog(node: ast.ClassDef) -> bool:
    for child in node.body:
        if isinstance(child, ast.FunctionDef) and child.name == "compose":
            for call in (item for item in ast.walk(child) if isinstance(item, ast.Call)):
                if not isinstance(call.func, ast.Name) or call.func.id != "RichLog":
                    continue
                for keyword in call.keywords:
                    if keyword.arg == "id" and isinstance(keyword.value, ast.Constant):
                        if keyword.value.value == "transcript":
                            return True
    return False


def _hint_failures(path: Path) -> list[str]:
    if not path.exists():
        return [f"{_display_path(path)}: missing selection hint module"]
    text = path.read_text(encoding="utf-8")
    failures = [
        f"{_display_path(path)}: stale selection hint contains {term!r}"
        for term in STALE_HINT_TERMS
        if term in text
    ]
    if "click and drag" not in text or "copy shortcut" not in text:
        failures.append(
            f"{_display_path(path)}: selection hint must mention click-drag and copy shortcut"
        )
    return failures


def _theme_failures(path: Path) -> list[str]:
    if not path.exists():
        return [f"{_display_path(path)}: missing theme"]
    text = path.read_text(encoding="utf-8")
    if "screen--selection" not in text:
        return [f"{_display_path(path)}: missing Screen > .screen--selection rule"]
    if "background:" not in text or "color:" not in text:
        return [f"{_display_path(path)}: selection rule must set background and color"]
    return []


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
