"""Validate sensitive interactive prompts map to secret-safe modal screens."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from craik.cli import app  # noqa: E402
from craik.runtime.contract.auto_registry import AutoSlashRegistry  # noqa: E402
from craik.runtime.shell.modals.guards import modal_security_failures  # noqa: E402


def main() -> int:
    failures = modal_security_failures(AutoSlashRegistry.from_typer(app))
    if failures:
        print("Modal screen security guard failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Modal screen security guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
