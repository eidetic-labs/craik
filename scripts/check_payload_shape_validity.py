"""Verify @craik_command(payload_shape=...) values are legal."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import get_args

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from craik.runtime.contract.command_result import PayloadShape  # noqa: E402

LEGAL_SHAPES = set(get_args(PayloadShape))


def main() -> int:
    failures = payload_shape_validity_failures(ROOT)
    if failures:
        print("Payload shape validity guard failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Payload shape validity guard passed.")
    return 0


def payload_shape_validity_failures(root: Path) -> list[str]:
    """Return @craik_command payload_shape declarations outside PayloadShape."""
    failures: list[str] = []
    for path in _cli_files(root):
        relative = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _name(node.func) != "craik_command":
                continue
            payload_shape = _keyword_value(node, "payload_shape")
            if payload_shape is None:
                continue
            if not isinstance(payload_shape, ast.Constant) or not isinstance(
                payload_shape.value, str
            ):
                failures.append(
                    f"{relative}:{_line_number(payload_shape)} "
                    "payload_shape must be a string literal"
                )
                continue
            if payload_shape.value not in LEGAL_SHAPES:
                failures.append(
                    f"{relative}:{_line_number(payload_shape)} "
                    f"payload_shape={payload_shape.value!r} "
                    f"is not legal; expected one of {sorted(LEGAL_SHAPES)!r}"
                )
    return failures


def _cli_files(root: Path) -> list[Path]:
    src = root / "src" / "craik"
    files = [src / "cli.py"]
    files.extend(sorted(src.glob("cli_*.py")))
    files.extend(sorted((src / "cli_new").glob("*.py")))
    return [path for path in files if path.exists()]


def _keyword_value(node: ast.Call, keyword: str) -> ast.AST | None:
    for candidate in node.keywords:
        if candidate.arg == keyword:
            return candidate.value
    return None


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _line_number(node: ast.AST) -> int:
    return getattr(node, "lineno", 0)


if __name__ == "__main__":
    raise SystemExit(main())
