"""Generate or check slash-command renderer snapshots at fixed widths."""

from __future__ import annotations

import argparse
import io
import os
import sys
import tempfile
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from rich.console import Console

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore  # noqa: E402
from craik.runtime.shell.slash_commands import dispatch_slash_command  # noqa: E402
from craik.runtime.shell.textual_widgets.slash_renderers import (  # noqa: E402
    _empty_state_payload,
    render_slash_payload,
)

DEFAULT_WIDTHS: tuple[int, ...] = (60, 80, 100, 120, 160, 200)
DEFAULT_OUTPUT_ROOT = ROOT / "tests" / "snapshots" / "slash"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    widths = tuple(args.width or DEFAULT_WIDTHS)
    env_updates = {}
    if args.craik_home:
        env_updates["CRAIK_HOME"] = str(args.craik_home)

    if args.name is None:
        args.name = _snapshot_name(args.command)

    temp_home: tempfile.TemporaryDirectory[str] | None = None
    if "CRAIK_HOME" not in env_updates:
        temp_home = tempfile.TemporaryDirectory(dir="/tmp", prefix="craik-snap-")
        env_updates["CRAIK_HOME"] = temp_home.name
    try:
        if args.with_operator_session:
            _seed_operator_session(Path(env_updates["CRAIK_HOME"]))
        snapshots = render_snapshots(
            args.command,
            widths=widths,
            env_updates=env_updates,
        )
        failures = write_or_check_snapshots(
            snapshots,
            output_root=args.output_root,
            name=args.name,
            check=args.check,
        )
    finally:
        if temp_home is not None:
            temp_home.cleanup()
    if failures:
        print("Snapshot generation check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    action = "checked" if args.check else "wrote"
    print(f"Slash snapshots {action} for {args.name}: {', '.join(map(str, widths))}")
    return 0


def render_snapshots(
    command: str,
    *,
    widths: Iterable[int] = DEFAULT_WIDTHS,
    env_updates: dict[str, str] | None = None,
) -> dict[int, str]:
    """Render one slash command at each requested width."""
    previous = {key: os.environ.get(key) for key in (env_updates or {})}
    os.environ.update(env_updates or {})
    try:
        result = dispatch_slash_command(command, env=os.environ.copy())
        renderable = _result_renderable(result)
        rendered = {width: _capture(renderable, width=width) for width in widths}
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    craik_home = (env_updates or {}).get("CRAIK_HOME")
    if craik_home:
        replacements = {craik_home, str(Path(craik_home).resolve())}
        rendered = {
            width: _replace_all(text, replacements, "<craik-home>")
            for width, text in rendered.items()
        }
    return rendered


def _result_renderable(result: Any) -> object:
    if getattr(result, "empty_state_message", None) is not None:
        return _empty_state_payload(result)
    payload = getattr(result, "payload", None)
    shape = getattr(result, "payload_shape", None)
    if payload is not None and shape is not None:
        return render_slash_payload(payload, shape=shape)
    return getattr(result, "text", result)


def write_or_check_snapshots(
    snapshots: dict[int, str],
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    name: str,
    check: bool,
) -> list[str]:
    """Write snapshots or return drift failures in check mode."""
    failures: list[str] = []
    target_dir = output_root / name
    if not check:
        target_dir.mkdir(parents=True, exist_ok=True)
    for width, text in sorted(snapshots.items()):
        path = target_dir / f"width-{width}.txt"
        normalized = _rstrip_lines(text)
        if check:
            if not path.exists():
                failures.append(f"{_display_path(path)} is missing")
                continue
            expected = _rstrip_lines(path.read_text(encoding="utf-8"))
            if normalized != expected:
                failures.append(f"{_display_path(path)} is stale")
            continue
        path.write_text(f"{normalized}\n", encoding="utf-8")
    return failures


def _capture(renderable: Any, *, width: int) -> str:
    console = Console(
        color_system=None,
        file=io.StringIO(),
        force_terminal=False,
        record=True,
        width=width,
    )
    console.print(renderable)
    return console.export_text()


def _rstrip_lines(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.splitlines())


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _replace_all(value: str, needles: set[str], replacement: str) -> str:
    for needle in sorted(needles, key=len, reverse=True):
        value = value.replace(needle, replacement)
    return value


def _seed_operator_session(home: Path) -> None:
    """Write a deterministic non-refreshing operator session for snapshot renders."""
    OperatorSessionStore(home).put(
        OperatorSession(
            subject="snapshot-operator",
            email="snapshot@example.invalid",
            display_name="Snapshot Operator",
            groups=["snapshot"],
            issuer="https://snapshot.example.invalid",
            id_token_jti="snapshot-token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
    )


def _snapshot_name(command: str) -> str:
    tokens = command.strip().split()
    if not tokens:
        raise ValueError("command must not be empty")
    return tokens[0].lstrip("/").replace("-", "_")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", help='Slash command text, for example "/status".')
    parser.add_argument("--name", help="Snapshot directory name. Defaults to command name.")
    parser.add_argument(
        "--width",
        action="append",
        type=int,
        choices=DEFAULT_WIDTHS,
        help="Snapshot width. Repeatable; defaults to all standard widths.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Root directory for slash snapshots.",
    )
    parser.add_argument("--craik-home", type=Path, help="CRAIK_HOME to use while rendering.")
    parser.add_argument(
        "--with-operator-session",
        action="store_true",
        help="Seed a deterministic operator session before rendering.",
    )
    parser.add_argument("--check", action="store_true", help="Check existing snapshots for drift.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
