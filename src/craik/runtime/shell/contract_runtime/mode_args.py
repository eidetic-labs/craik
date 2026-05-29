"""Argument helpers for Claude permission mode slash commands."""

from __future__ import annotations

CLAUDE_PERMISSION_MODE_CHOICES = (
    "ask",
    "auto",
    "acceptEdits",
    "plan",
    "dontAsk",
    "bypassPermissions",
)


def stored_permission_mode(mode: str) -> str:
    if mode in {"ask", "default"}:
        return "default"
    if mode in CLAUDE_PERMISSION_MODE_CHOICES:
        return mode
    raise ValueError(mode)


def display_permission_mode(mode: str) -> str:
    return "ask" if mode == "default" else mode
