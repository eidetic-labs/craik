"""File mention completion helpers for @filename input."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from textual.widgets import OptionList


@dataclass(frozen=True)
class FileCompletion:
    """One file mention completion candidate."""

    token: str
    path: Path


class FileCompletionPopup(OptionList):
    """Popup list populated from workspace file candidates."""


def file_completion_candidates(
    prefix: str,
    *,
    root: Path | None = None,
    limit: int = 20,
) -> list[FileCompletion]:
    """Return @mention file candidates below ``root``."""
    base = root or Path.cwd()
    normalized = prefix.removeprefix("@")
    candidates: list[FileCompletion] = []
    if not base.exists():
        return candidates
    for path in sorted(base.rglob("*")):
        if len(candidates) >= limit:
            break
        if not path.is_file() or ".git" in path.parts:
            continue
        relative = path.relative_to(base).as_posix()
        if normalized and not relative.startswith(normalized):
            continue
        candidates.append(FileCompletion(token=f"@{relative}", path=path))
    return candidates
