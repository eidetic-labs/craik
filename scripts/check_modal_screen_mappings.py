"""Validate interactive prompt metadata resolves to canonical TUI modals."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from craik.cli import app  # noqa: E402
from craik.runtime.contract.auto_registry import AutoSlashRegistry  # noqa: E402
from craik.runtime.shell.modals.guards import modal_mapping_failures  # noqa: E402


def main() -> int:
    failures = [
        *modal_mapping_failures(AutoSlashRegistry.from_typer(app)),
        *prompt_metadata_failures(ROOT),
    ]
    if failures:
        print("Modal screen mapping guard failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Modal screen mapping guard passed.")
    return 0


def prompt_metadata_failures(root: Path) -> list[str]:
    """Return CLI prompt call sites without command modal metadata."""
    failures: list[str] = []
    for path in _cli_files(root):
        relative = path.relative_to(root).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        tree = ast.parse("\n".join(lines))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or not _contains_typer_prompt(node):
                continue
            if _craik_command_has_interactive_prompts(node):
                continue
            if _has_prompt_owner_marker(lines, node):
                continue
            failures.append(
                f"{relative}:{node.lineno} {node.name} uses typer prompt/confirm "
                "without interactive_prompts metadata or owner marker"
            )
    return failures


def _cli_files(root: Path) -> list[Path]:
    src = root / "src" / "craik"
    files = [src / "cli.py"]
    files.extend(sorted(src.glob("cli_*.py")))
    files.extend(sorted((src / "cli_new").glob("*.py")))
    return [path for path in files if path.exists()]


def _contains_typer_prompt(node: ast.FunctionDef) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if _name(child.func) in {"typer.prompt", "typer.confirm"}:
            return True
    return False


def _craik_command_has_interactive_prompts(node: ast.FunctionDef) -> bool:
    for decorator in node.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        if call is None or _name(call.func) != "craik_command":
            continue
        for keyword in call.keywords:
            if keyword.arg != "interactive_prompts":
                continue
            if isinstance(keyword.value, ast.Dict) and keyword.value.keys:
                return True
    return False


def _has_prompt_owner_marker(lines: list[str], node: ast.FunctionDef) -> bool:
    start = max(0, node.lineno - 4)
    end = max(0, node.lineno - 1)
    return any("craik-interactive-prompt-owner:" in line for line in lines[start:end])


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


if __name__ == "__main__":
    raise SystemExit(main())
