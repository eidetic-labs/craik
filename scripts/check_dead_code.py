"""Complementary to check_release_readiness.py.

Catches broader dead-code shapes (unused functions, classes, arguments) the
structural guard doesn't model.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    root = Path(os.environ.get("CRAIK_DEAD_CODE_ROOT", ROOT)).resolve()
    src_path = root / "src" / "craik"
    whitelist_path = root / "vulture-whitelist.py"
    command = [
        sys.executable,
        "-m",
        "vulture",
        str(src_path),
    ]
    if whitelist_path.exists():
        command.append(str(whitelist_path))
    command.extend(["--min-confidence", "80"])
    return 0 if subprocess.run(command, cwd=root, check=False).returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
