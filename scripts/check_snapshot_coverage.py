"""Validate baseline slash snapshots exist for every registered slash command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from craik.runtime.shell.slash_command_schema import slash_command_specs  # noqa: E402

DEFAULT_SNAPSHOT_ROOT = ROOT / "tests" / "snapshots" / "slash"
DEFAULT_WIDTH = 80


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot-root",
        type=Path,
        default=DEFAULT_SNAPSHOT_ROOT,
        help="Root containing tests/snapshots/slash/<command>/width-<width>.txt files.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=DEFAULT_WIDTH,
        help="Required baseline width.",
    )
    args = parser.parse_args(argv)

    command_names = [spec.command_name for spec in slash_command_specs()]
    failures = snapshot_coverage_failures(
        command_names,
        snapshot_root=args.snapshot_root,
        width=args.width,
    )
    if failures:
        print("Slash snapshot coverage guard failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Slash snapshot coverage guard passed.")
    return 0


def snapshot_coverage_failures(
    command_names: list[str],
    *,
    snapshot_root: Path,
    width: int = DEFAULT_WIDTH,
) -> list[str]:
    """Return missing snapshot failures for registered slash command names."""
    failures: list[str] = []
    for command_name in command_names:
        expected = snapshot_root / command_name / f"width-{width}.txt"
        if not expected.is_file():
            failures.append(f"/{command_name}: missing {expected.relative_to(snapshot_root)}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
