"""Mode-scoped shell history persistence for the terminal UI."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore
from craik.runtime.auth.operator_modes import operator_session_required
from craik.runtime.paths import ensure_craik_home

DEFAULT_HISTORY_MAX_ENTRIES = 10_000


@dataclass(frozen=True)
class HistoryEntry:
    """One submitted shell prompt or slash command."""

    text: str
    created_at: datetime

    def as_json(self) -> str:
        return json.dumps(
            {"text": self.text, "created_at": self.created_at.isoformat()},
            sort_keys=True,
        )


def history_path(env: dict[str, str] | None = None) -> Path:
    """Return the history path for the current operator mode."""
    paths = ensure_craik_home(env)
    if not operator_session_required(env):
        return paths.state / "shell-history.jsonl"
    try:
        session = OperatorSessionStore.from_env(env).get()
    except OperatorSessionNotFoundError:
        return paths.state / "shell-history-anonymous.jsonl"
    subject_hash = hashlib.sha256(session.subject.encode("utf-8")).hexdigest()[:16]
    return paths.state / f"shell-history-{subject_hash}.jsonl"


def append_history(text: str, *, env: dict[str, str] | None = None) -> None:
    """Append one history entry, respecting max-entry rotation."""
    if _history_max_entries(env) == 0:
        return
    value = text.strip()
    if not value:
        return
    path = history_path(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_history(env=env)
    existing.append(HistoryEntry(value, datetime.now(UTC)))
    limit = _history_max_entries(env)
    retained = existing[-limit:] if limit > 0 else existing
    path.write_text("\n".join(entry.as_json() for entry in retained) + "\n", encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o600)


def read_history(*, env: dict[str, str] | None = None) -> list[HistoryEntry]:
    """Read history entries newest-last, ignoring malformed rows."""
    path = history_path(env)
    if not path.exists():
        return []
    entries: list[HistoryEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
            text = payload["text"]
            created_at = datetime.fromisoformat(payload["created_at"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(text, str):
            entries.append(HistoryEntry(text=text, created_at=created_at))
    return entries


def search_history(prefix: str = "", *, env: dict[str, str] | None = None) -> list[str]:
    """Return de-duplicated history values matching ``prefix`` newest-first."""
    seen: set[str] = set()
    matches: list[str] = []
    for entry in reversed(read_history(env=env)):
        if entry.text in seen:
            continue
        if prefix and not entry.text.startswith(prefix):
            continue
        seen.add(entry.text)
        matches.append(entry.text)
    return matches


def _history_max_entries(env: dict[str, str] | None) -> int:
    values = os.environ if env is None else env
    raw = values.get("CRAIK_HISTORY_MAX_ENTRIES")
    if raw is None:
        return DEFAULT_HISTORY_MAX_ENTRIES
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_HISTORY_MAX_ENTRIES
