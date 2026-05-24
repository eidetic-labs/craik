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
    css_paths = sorted(
        (root / "src" / "craik" / "runtime" / "shell").glob("textual_app_*.tcss")
    )
    if not app_path.exists() or not css_paths:
        return set()
    id_to_class = {
        match.group("id"): match.group("class")
        for match in _COMPOSE_YIELD_RE.finditer(app_path.read_text(encoding="utf-8"))
    }
    widgets: set[str] = set()
    for css_path in css_paths:
        if not css_path.is_file():
            continue
        for match in _CSS_ID_BLOCK_RE.finditer(css_path.read_text(encoding="utf-8")):
            if _DOCK_BOTTOM_RE.search(match.group("body")) and match.group("id") in id_to_class:
                widgets.add(id_to_class[match.group("id")])
    return widgets


def _region_y_covered_widgets(root: Path) -> set[str]:
    docked = bottom_docked_widgets(root)
    covered: set[str] = set()
    for path in (root / "tests").rglob("test*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                covered.update(_asserted_region_y_widgets(node, docked))
    return covered


def _asserted_region_y_widgets(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    docked: set[str],
) -> set[str]:
    bindings = _widget_bindings(function, docked)
    covered: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Assert):
            continue
        for sub in ast.walk(node.test):
            widget = _region_y_widget(sub, bindings, docked)
            if widget is not None:
                covered.add(widget)
    return covered


def _widget_bindings(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    docked: set[str],
) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for node in ast.walk(function):
        if isinstance(node, ast.Assign):
            widget = _query_one_widget(node.value, docked)
            if widget is None:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bindings[target.id] = widget
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            widget = _query_one_widget(node.value, docked) if node.value is not None else None
            if widget is not None:
                bindings[node.target.id] = widget
    return bindings


def _query_one_widget(node: ast.AST | None, docked: set[str]) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.func, ast.Attribute) or node.func.attr != "query_one":
        return None
    if not node.args or not isinstance(node.args[0], ast.Name):
        return None
    widget = node.args[0].id
    return widget if widget in docked else None


def _region_y_widget(
    node: ast.AST,
    bindings: dict[str, str],
    docked: set[str],
) -> str | None:
    if not isinstance(node, ast.Attribute) or node.attr != "y":
        return None
    if not isinstance(node.value, ast.Attribute) or node.value.attr != "region":
        return None
    owner = node.value.value
    if isinstance(owner, ast.Name):
        if owner.id in bindings:
            return bindings[owner.id]
        if owner.id in docked:
            return owner.id
    widget = _query_one_widget(owner, docked)
    return widget


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
