"""External editor round-trip support for the terminal UI."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess  # nosec B404 - external editor is an explicit operator action.
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from craik.runtime.paths import ensure_craik_home

EditorRunner = Callable[[Sequence[str]], int]


@dataclass(frozen=True)
class ExternalEditorResult:
    """Result of an external editor invocation."""

    text: str
    changed: bool
    warning: str | None = None


def edit_text_externally(
    text: str,
    *,
    env: dict[str, str] | None = None,
    runner: EditorRunner | None = None,
) -> ExternalEditorResult:
    """Open ``text`` in an external editor and return the edited value."""
    values = os.environ if env is None else env
    command = _editor_command(values)
    if command is None:
        return ExternalEditorResult(
            text=text,
            changed=False,
            warning="No external editor found; set EDITOR or VISUAL.",
        )

    path = _temp_editor_path(values)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o600)
    run = runner or _subprocess_runner
    try:
        exit_code = run([*command, str(path)])
        if exit_code != 0:
            return ExternalEditorResult(
                text=text,
                changed=False,
                warning=f"External editor exited with status {exit_code}; input unchanged.",
            )
        updated = path.read_text(encoding="utf-8")
        return ExternalEditorResult(text=updated, changed=updated != text)
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _editor_command(env: os._Environ[str] | dict[str, str]) -> list[str] | None:
    for key in ("EDITOR", "VISUAL"):
        raw = env.get(key)
        if raw and raw.strip():
            return shlex.split(raw)
    vi = shutil.which("vi")
    return [vi] if vi else None


def _temp_editor_path(env: os._Environ[str] | dict[str, str]) -> Path:
    paths = ensure_craik_home(dict(env))
    return paths.state / "external-editor" / f"{uuid.uuid4().hex}.txt"


def _subprocess_runner(command: Sequence[str]) -> int:
    # shell=False with a shlex-split operator editor command avoids shell injection.
    return subprocess.run(command, check=False).returncode  # nosec B603
