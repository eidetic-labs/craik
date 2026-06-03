"""Tests for the hook-settings registration util (Wire-T1).

Covers the pure ``merge_hook_settings`` deep-merge (preserve existing hooks,
append craik's entry, idempotency, keep an operator's conflicting same-event
hook) and the ``registered_hook_settings`` context manager's restore-on-exit /
restore-on-exception / remove-a-file-that-did-not-exist behaviour, plus the
standalone craik-owned-file writer (used for the ``claude --settings`` path).
Pure-function and ``tmp_path`` filesystem tests only -- no CLI binaries.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from craik.runtime.backend.adapters.hook_settings import (
    HOOK_COMMAND,
    merge_hook_settings,
    registered_hook_settings,
    write_hook_settings_file,
)

# A ``.claude/settings.json``-shaped craik hook block, matching what
# ``_pre_tool_use_hook_config()["settings"]`` produces.
_CRAIK_BLOCK = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "*",
                "hooks": [{"type": "command", "command": HOOK_COMMAND}],
            }
        ]
    }
}

# A ``.gemini/settings.json``-shaped craik hook block (BeforeTool event).
_CRAIK_GEMINI_BLOCK = {
    "hooks": {
        "BeforeTool": [
            {
                "matcher": "*",
                "hooks": [{"type": "command", "command": HOOK_COMMAND}],
            }
        ]
    }
}


def test_merge_into_empty_adds_craik_hook() -> None:
    merged = merge_hook_settings({}, _CRAIK_BLOCK)
    assert merged == _CRAIK_BLOCK
    # Pure: input dict not mutated.
    assert merge_hook_settings({}, _CRAIK_BLOCK) is not _CRAIK_BLOCK


def test_merge_preserves_unrelated_existing_keys() -> None:
    existing = {
        "model": "claude-x",
        "permissions": {"allow": ["Read"]},
        "hooks": {"PostToolUse": [{"matcher": "*", "hooks": []}]},
    }
    merged = merge_hook_settings(existing, _CRAIK_BLOCK)
    assert merged["model"] == "claude-x"
    assert merged["permissions"] == {"allow": ["Read"]}
    # The operator's unrelated PostToolUse hook survives untouched.
    assert merged["hooks"]["PostToolUse"] == [{"matcher": "*", "hooks": []}]
    # craik's PreToolUse entry is appended.
    assert _CRAIK_BLOCK["hooks"]["PreToolUse"][0] in merged["hooks"]["PreToolUse"]


def test_merge_does_not_mutate_existing() -> None:
    existing = {"hooks": {"PreToolUse": []}}
    snapshot = json.dumps(existing, sort_keys=True)
    merge_hook_settings(existing, _CRAIK_BLOCK)
    assert json.dumps(existing, sort_keys=True) == snapshot


def test_merge_is_idempotent() -> None:
    once = merge_hook_settings({}, _CRAIK_BLOCK)
    twice = merge_hook_settings(once, _CRAIK_BLOCK)
    assert twice == once
    # Exactly one craik entry, no duplicate.
    entries = twice["hooks"]["PreToolUse"]
    craik_entries = [
        e
        for e in entries
        if any(h.get("command") == HOOK_COMMAND for h in e.get("hooks", []))
    ]
    assert len(craik_entries) == 1


def test_merge_keeps_operator_conflicting_same_event_hook() -> None:
    existing = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": "operator-own-hook"}],
                }
            ]
        }
    }
    merged = merge_hook_settings(existing, _CRAIK_BLOCK)
    entries = merged["hooks"]["PreToolUse"]
    commands = [
        h.get("command") for e in entries for h in e.get("hooks", [])
    ]
    # Both the operator's hook and craik's hook are present (additive).
    assert "operator-own-hook" in commands
    assert HOOK_COMMAND in commands


def test_merge_handles_gemini_before_tool_event() -> None:
    existing = {"hooks": {"BeforeTool": [{"matcher": "src/**", "hooks": []}]}}
    merged = merge_hook_settings(existing, _CRAIK_GEMINI_BLOCK)
    entries = merged["hooks"]["BeforeTool"]
    assert {"matcher": "src/**", "hooks": []} in entries
    assert _CRAIK_GEMINI_BLOCK["hooks"]["BeforeTool"][0] in entries


def test_context_manager_restores_original_bytes_on_exit(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    original = '{\n  "model": "claude-x",\n  "hooks": {"PreToolUse": []}\n}\n'
    settings.write_text(original, encoding="utf-8")

    with registered_hook_settings(settings, _CRAIK_BLOCK):
        during = json.loads(settings.read_text(encoding="utf-8"))
        commands = [
            h.get("command")
            for e in during["hooks"]["PreToolUse"]
            for h in e.get("hooks", [])
        ]
        assert HOOK_COMMAND in commands
        assert during["model"] == "claude-x"

    # Byte-for-byte restore.
    assert settings.read_text(encoding="utf-8") == original


def test_context_manager_restores_on_exception(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    original = '{"existing": true}'
    settings.write_text(original, encoding="utf-8")

    with pytest.raises(RuntimeError):
        with registered_hook_settings(settings, _CRAIK_BLOCK):
            assert HOOK_COMMAND in settings.read_text(encoding="utf-8")
            raise RuntimeError("boom")

    assert settings.read_text(encoding="utf-8") == original


def test_context_manager_removes_file_that_did_not_exist(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    assert not settings.exists()

    with registered_hook_settings(settings, _CRAIK_BLOCK):
        # craik's settings are written for the duration of the run.
        assert settings.exists()
        commands = [
            h.get("command")
            for e in json.loads(settings.read_text())["hooks"]["PreToolUse"]
            for h in e.get("hooks", [])
        ]
        assert HOOK_COMMAND in commands

    # Removed on exit because it did not exist before.
    assert not settings.exists()


def test_context_manager_removes_file_that_did_not_exist_on_exception(
    tmp_path: Path,
) -> None:
    settings = tmp_path / "settings.json"
    with pytest.raises(RuntimeError):
        with registered_hook_settings(settings, _CRAIK_BLOCK):
            assert settings.exists()
            raise RuntimeError("boom")
    assert not settings.exists()


def test_write_hook_settings_file_writes_standalone_block(tmp_path: Path) -> None:
    target = tmp_path / "craik-settings.json"
    write_hook_settings_file(target, _CRAIK_BLOCK)
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written == _CRAIK_BLOCK


def test_write_hook_settings_file_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "settings.json"
    write_hook_settings_file(target, _CRAIK_BLOCK)
    assert target.exists()
