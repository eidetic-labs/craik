"""Guard CLI/TUI shared commands against direct JSON stdout writes."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "craik"

_DIRECT_JSON_STDOUT_NAMES = {"print", "typer.echo", "sys.stdout.write"}


def main() -> int:
    failures = direct_stdout_failures(ROOT)
    if failures:
        print("Direct stdout guard failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Direct stdout guard passed.")
    return 0


def direct_stdout_failures(root: Path) -> list[str]:
    """Return direct JSON stdout violations for shared command callbacks."""
    failures: list[str] = []
    for path in _cli_files(root):
        relative = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if _has_tui_eligible_craik_command(node):
                for call in _direct_json_stdout_calls(node):
                    failures.append(
                        f"{relative}:{call.lineno} {node.name} emits JSON directly; "
                        "use craik.cli_output.emit_command_result(result)"
                    )
    return failures


def _cli_files(root: Path) -> list[Path]:
    src = root / "src" / "craik"
    files = [*src.glob("cli*.py"), *(src / "cli_new").glob("*.py")]
    return sorted({path for path in files if path.is_file()})


def _has_tui_eligible_craik_command(node: ast.FunctionDef) -> bool:
    for decorator in node.decorator_list:
        if _decorator_name(decorator) != "craik_command":
            continue
        if isinstance(decorator, ast.Call):
            for keyword in decorator.keywords:
                if (
                    keyword.arg == "tui_eligible"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is False
                ):
                    return False
        return True
    return False


def _decorator_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        return _callable_name(node.func)
    return _callable_name(node)


def _direct_json_stdout_calls(node: ast.FunctionDef) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        if _callable_name(call.func) not in _DIRECT_JSON_STDOUT_NAMES:
            continue
        if not call.args or not isinstance(call.args[0], ast.Call):
            continue
        if _callable_name(call.args[0].func) == "json.dumps":
            calls.append(call)
    return calls


def _callable_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _callable_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


if __name__ == "__main__":
    raise SystemExit(main())
