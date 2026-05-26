"""Validate baseline slash snapshots exist for every registered slash command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from craik.runtime.shell.slash_command_schema import SlashCommandSpec, slash_command_specs  # noqa: E402,I001

DEFAULT_SNAPSHOT_ROOT = ROOT / "tests" / "snapshots" / "slash"
DEFAULT_WIDTH = 80
STANDARD_WIDTHS: tuple[int, ...] = (60, 80, 100, 120, 160, 200)
FULL_WIDTH_SHAPES = frozenset({"table", "card", "card_list"})


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

    failures = snapshot_coverage_failures(
        slash_command_specs(),
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
    specs: list[SlashCommandSpec] | list[str],
    *,
    snapshot_root: Path,
    width: int = DEFAULT_WIDTH,
) -> list[str]:
    """Return missing snapshot failures for registered slash command names."""
    failures: list[str] = []
    for spec in specs:
        required_widths: tuple[int, ...]
        if isinstance(spec, str):
            command_name = spec
            required_widths = (width,)
        else:
            command_name = spec.command_name
            required_widths = (
                STANDARD_WIDTHS if spec.payload_shape in FULL_WIDTH_SHAPES else (width,)
            )
        for required_width in required_widths:
            expected = snapshot_root / command_name / f"width-{required_width}.txt"
            if not expected.is_file():
                failures.append(f"/{command_name}: missing {expected.relative_to(snapshot_root)}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
