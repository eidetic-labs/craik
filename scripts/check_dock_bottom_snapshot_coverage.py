"""Require rendered-region snapshot coverage for bottom-docked TUI widgets."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_DOCK_BOTTOM_RE = re.compile(r"dock\s*:\s*bottom")
_CSS_ID_BLOCK_RE = re.compile(r"#(?P<id>[a-zA-Z0-9_-]+)\s*\{(?P<body>.*?)\}", re.DOTALL)
_COMPOSE_YIELD_RE = re.compile(
    r"yield\s+(?P<class>[A-Z][A-Za-z0-9_]*)\([^)]*id=[\"'](?P<id>[a-zA-Z0-9_-]+)[\"']",
    re.DOTALL,
)


def bottom_docked_widgets(root: Path = ROOT) -> set[str]:
    """Return widget class names that render in the TUI bottom dock."""
    widgets = _default_css_bottom_widgets(root)
    widgets.update(_stylesheet_bottom_widgets(root))
    return widgets


def missing_snapshot_coverage(root: Path = ROOT) -> list[str]:
    """Return bottom-docked widgets missing rendered ``region.y`` test coverage."""
    covered = _region_y_covered_widgets(root)
    return sorted(widget for widget in bottom_docked_widgets(root) if widget not in covered)


def _default_css_bottom_widgets(root: Path) -> set[str]:
    widgets: set[str] = set()
    for path in (root / "src" / "craik" / "runtime" / "shell").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for statement in node.body:
                if not isinstance(statement, ast.Assign):
                    continue
                if not any(
                    isinstance(target, ast.Name) and target.id == "DEFAULT_CSS"
                    for target in statement.targets
                ):
                    continue
                css = _string_assignment_value(statement.value, source)
                if css is not None and _DOCK_BOTTOM_RE.search(css):
                    widgets.add(node.name)
    return widgets


def _string_assignment_value(node: ast.AST, source: str) -> str | None:
    try:
        value = ast.literal_eval(node)
    except ValueError:
        return ast.get_source_segment(source, node)
    return value if isinstance(value, str) else None


def _stylesheet_bottom_widgets(root: Path) -> set[str]:
    app_path = root / "src" / "craik" / "runtime" / "shell" / "textual_app.py"
    css_path = root / "src" / "craik" / "runtime" / "shell" / "textual_app_dark.tcss"
    if not app_path.exists() or not css_path.exists():
        return set()
    id_to_class = {
        match.group("id"): match.group("class")
        for match in _COMPOSE_YIELD_RE.finditer(app_path.read_text(encoding="utf-8"))
    }
    widgets: set[str] = set()
    for match in _CSS_ID_BLOCK_RE.finditer(css_path.read_text(encoding="utf-8")):
        if _DOCK_BOTTOM_RE.search(match.group("body")) and match.group("id") in id_to_class:
            widgets.add(id_to_class[match.group("id")])
    return widgets


def _region_y_covered_widgets(root: Path) -> set[str]:
    covered: set[str] = set()
    for path in (root / "tests").rglob("test*.py"):
        text = path.read_text(encoding="utf-8")
        if "region.y" not in text:
            continue
        for widget in bottom_docked_widgets(root):
            if widget in text:
                covered.add(widget)
    return covered


def main() -> int:
    missing = missing_snapshot_coverage()
    if missing:
        print("Bottom-docked widgets missing region.y snapshot coverage:")
        for widget in missing:
            print(f"  {widget}")
        return 1
    print("Bottom-docked widget snapshot coverage is present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
