"""Register craik's live pre-tool hook into a vendor CLI run, safely.

Foundation for wiring craik's ``craik-hook`` PreToolUse/BeforeTool hook into a
real vendor CLI run WITHOUT clobbering the operator's own settings. This module
is the registration *mechanism* + the merge math; the live ``spawn`` wiring is a
later task and is not done here.

Mechanism per vendor (Part A spike findings):

* **Anthropic ``claude``** accepts ``--settings <file-or-json>`` (documented in
  code.claude.com/docs/en/headless.md, bare-mode "To load ... Settings" table).
  So craik can point the run at a *craik-owned* standalone settings file via
  :func:`write_hook_settings_file` and pass ``--settings <that file>`` -- the
  operator's tracked ``.claude/settings.json`` is never touched. (Preferred.)
* **Gemini ``gemini``** has NO per-run settings-path flag. Its only path
  overrides are ``GEMINI_CLI_SYSTEM_SETTINGS_PATH`` /
  ``GEMINI_CLI_SYSTEM_DEFAULTS_PATH`` (system-level, not a clean per-run knob;
  reference/configuration.md). So gemini must fall back to merging craik's hook
  into the project ``.gemini/settings.json`` and restoring it on teardown.

:func:`merge_hook_settings` is the robust fallback used by gemini (and available
to claude); :func:`registered_hook_settings` is the merge-and-restore context
manager that performs it fail-safe. Both are exercised by the live spawn in the
next task; nothing here starts a subprocess or a daemon.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# The ``craik-hook`` console script (pyproject entry point
# ``craik.runtime.hooks.client:craik_hook_main``). Idempotency keys on this
# command string: a merge that already contains a hook entry invoking it is a
# no-op.
HOOK_COMMAND = "craik-hook"


def _entry_invokes_craik(entry: dict[str, Any]) -> bool:
    """True when a settings hook ``entry`` already runs the craik-hook command."""
    inner = entry.get("hooks")
    if not isinstance(inner, list):
        return False
    return any(
        isinstance(h, dict) and h.get("command") == HOOK_COMMAND for h in inner
    )


def merge_hook_settings(existing: dict[str, Any], hook_block: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge craik's ``hook_block`` into an ``existing`` settings dict.

    Pure (no I/O, no mutation of either argument). Rules:

    * Preserve ALL existing keys and hook entries.
    * For each event in ``hook_block["hooks"]`` (e.g. ``PreToolUse`` /
      ``BeforeTool``), APPEND craik's entry to that event's array rather than
      replacing it.
    * Idempotent: if the event array already contains an entry invoking
      :data:`HOOK_COMMAND`, craik's entry is not appended again.
    * An operator's own hook on the SAME event is kept; craik's is purely
      additive.
    """
    merged = copy.deepcopy(existing)
    incoming_hooks = hook_block.get("hooks")
    if not isinstance(incoming_hooks, dict):
        return merged

    hooks = merged.setdefault("hooks", {})
    if not isinstance(hooks, dict):  # defensive: operator put a non-dict here
        return merged

    for event, craik_entries in incoming_hooks.items():
        if not isinstance(craik_entries, list):
            continue
        target = hooks.setdefault(event, [])
        if not isinstance(target, list):
            continue
        if any(
            isinstance(e, dict) and _entry_invokes_craik(e) for e in target
        ):
            continue  # craik already registered on this event -> idempotent
        for entry in craik_entries:
            target.append(copy.deepcopy(entry))
    return merged


def write_hook_settings_file(target: Path, hook_block: dict[str, Any]) -> None:
    """Write ``hook_block`` as a standalone craik-owned settings file.

    Used for the preferred Anthropic path: the run is launched with
    ``claude --settings <target>`` so the operator's own ``.claude/settings.json``
    is never mutated. Creates parent directories as needed.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(hook_block, indent=2) + "\n", encoding="utf-8")


@contextmanager
def registered_hook_settings(settings_path: Path, hook_block: dict[str, Any]) -> Iterator[Path]:
    """Temporarily merge craik's hook into ``settings_path``, restoring on exit.

    Fallback registration path (mandatory for gemini's ``.gemini/settings.json``,
    available for claude's ``.claude/settings.json``). On entry:

    * Read the existing settings (``{}`` if the file is absent or empty), merge
      craik's ``hook_block`` via :func:`merge_hook_settings`, and write the
      result to ``settings_path`` (creating parent dirs).

    On exit -- whether normally OR via an exception -- the ORIGINAL state is
    restored fail-safe:

    * If the file existed before, its exact original bytes are rewritten.
    * If it did not exist before, it is removed (parent dirs left as-is).

    Yields ``settings_path`` for convenience.
    """
    existed = settings_path.exists()
    original_bytes = settings_path.read_bytes() if existed else None

    if original_bytes:
        try:
            existing = json.loads(original_bytes.decode("utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except (ValueError, UnicodeDecodeError):
            existing = {}
    else:
        existing = {}

    merged = merge_hook_settings(existing, hook_block)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")

    try:
        yield settings_path
    finally:
        if existed and original_bytes is not None:
            settings_path.write_bytes(original_bytes)
        else:
            settings_path.unlink(missing_ok=True)


__all__ = [
    "HOOK_COMMAND",
    "merge_hook_settings",
    "registered_hook_settings",
    "write_hook_settings_file",
]
