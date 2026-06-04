"""Pin that a GATED CLI run for a hook-capable vendor REGISTERS the craik-hook.

A future refactor must not be able to silently drop a "gated" run back to an
ungated-while-claiming-gated state -- a run that opens the bridge but never
registers craik's pre-tool hook with the vendor CLI would let every tool call
proceed unreviewed while still presenting as governed. This guard makes that
regression class un-mergeable for the two hook-capable vendors (anthropic-cli /
google-cli; openai-cli is observe-only and is NOT gated, so it is excluded).

It drives the REAL production gating-config code (no AST parsing, no subprocess):

* **Claude (anthropic-cli)** -- ``claude_gate_settings(gated=True, ...)`` is the
  function ``_execute_claude_code_prompt`` calls on the gated path; this guard
  enters it and asserts it yields a ``--settings`` file path whose contents carry
  a ``PreToolUse`` hook invoking ``craik-hook`` (Wire-T2). A gated run that
  produced no ``--settings`` path, or a settings file without the craik-hook,
  FAILS here.
* **Gemini (google-cli)** -- the gated ``run()`` merges
  ``_before_tool_hook_config()["settings"]`` into ``.gemini/settings.json`` via
  ``merge_hook_settings`` (Wire-T3, since gemini has no per-run ``--settings``
  flag). This guard runs that real merge against a representative operator
  settings dict and asserts a ``BeforeTool`` craik-hook entry results AND the
  operator's own hooks are preserved.

Fail-loud: the guard has no external input; if the REAL config functions cannot
be imported or do not register the hook, it exits non-zero.
"""

from __future__ import annotations

import sys
from typing import Any

HOOK_COMMAND = "craik-hook"


def _entry_invokes_craik(entry: dict[str, Any]) -> bool:
    """True when a settings hook ``entry`` runs the craik-hook command."""
    inner = entry.get("hooks")
    if not isinstance(inner, list):
        return False
    return any(isinstance(h, dict) and h.get("command") == HOOK_COMMAND for h in inner)


def _event_has_craik_hook(settings: dict[str, Any], event: str) -> bool:
    """True when ``settings["hooks"][event]`` contains a craik-hook entry."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return False
    entries = hooks.get(event)
    if not isinstance(entries, list):
        return False
    return any(isinstance(e, dict) and _entry_invokes_craik(e) for e in entries)


def check_claude() -> list[str]:
    """A gated claude run must yield a --settings file registering the craik-hook."""
    import json

    from craik.runtime.backend.adapters.anthropic_cli import _pre_tool_use_hook_config
    from craik.runtime.backend.adapters.hook_settings import claude_gate_settings

    failures: list[str] = []
    hook_block = _pre_tool_use_hook_config()["settings"]

    # Drive the REAL gated path: gated=True forces a fail-safe gate AND writes a
    # craik-owned --settings file (the wiring _execute_claude_code_prompt uses).
    with claude_gate_settings(operator_mode=None, gated=True, hook_block=hook_block) as gate:
        if gate.settings_path is None:
            failures.append(
                "anthropic-cli: gated run produced NO --settings path"
                " -- the craik PreToolUse hook would not be registered (ungated-while-gated)."
            )
            return failures
        try:
            written = json.loads(gate.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            failures.append(f"anthropic-cli: gated --settings file unreadable: {exc}")
            return failures
        if not _event_has_craik_hook(written, "PreToolUse"):
            failures.append(
                "anthropic-cli: gated --settings file has NO PreToolUse craik-hook"
                f" -- registered events: {sorted((written.get('hooks') or {}).keys())}."
            )

    return failures


def check_gemini() -> list[str]:
    """A gated gemini run must MERGE a BeforeTool craik-hook (preserving operator's)."""
    from craik.runtime.backend.adapters.google_cli import _before_tool_hook_config
    from craik.runtime.backend.adapters.hook_settings import merge_hook_settings

    failures: list[str] = []
    hook_block = _before_tool_hook_config()["settings"]

    # A representative operator settings dict with its OWN BeforeTool hook: the
    # merge must ADD craik's without dropping the operator's (additive contract).
    operator_settings: dict[str, Any] = {
        "hooks": {
            "BeforeTool": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "operator-own-hook"}]}
            ]
        }
    }
    merged = merge_hook_settings(operator_settings, hook_block)

    if not _event_has_craik_hook(merged, "BeforeTool"):
        failures.append(
            "google-cli: gated run merge produced NO BeforeTool craik-hook"
            " -- the gemini pre-tool gate would not fire (ungated-while-gated)."
        )

    # The operator's own hook must survive (the merge is additive, not a clobber).
    before_tool = merged.get("hooks", {}).get("BeforeTool", [])
    operator_preserved = any(
        isinstance(e, dict)
        and any(
            isinstance(h, dict) and h.get("command") == "operator-own-hook"
            for h in e.get("hooks", [])
        )
        for e in before_tool
    )
    if not operator_preserved:
        failures.append(
            "google-cli: merging craik's BeforeTool hook CLOBBERED the operator's own hook"
            " -- registration must be additive."
        )

    return failures


def main() -> int:
    failures: list[str] = []
    try:
        failures.extend(check_claude())
        failures.extend(check_gemini())
    except Exception as exc:  # noqa: BLE001 -- fail-loud: any import/wiring break is a fail
        print(
            f"Gated-run hook-registration guard ERRORED (treated as failure): {exc!r}",
            file=sys.stderr,
        )
        return 1

    if failures:
        print("Gated-run hook-registration guard failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(
        "Gated-run hook-registration guard passed: a gated anthropic-cli run registers a"
        " PreToolUse craik-hook (via --settings) and a gated google-cli run merges a"
        " BeforeTool craik-hook (preserving the operator's own hooks)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
