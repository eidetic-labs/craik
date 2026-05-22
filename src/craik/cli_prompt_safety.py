"""Prompt-input safety helpers for CLI commands."""

from __future__ import annotations

import sys

import typer

ARGV_PROMPT_ERROR = (
    "Error: argv-supplied prompts are visible to local processes via 'ps' "
    "and shell history. Either pipe via stdin ('-') or pass "
    "--allow-argv-prompt to acknowledge the exposure."
)
ARGV_PROMPT_WARNING = (
    "WARNING: prompt was supplied via argv; visible to local processes "
    "and shell history. Use '-' next time for stdin."
)


def resolve_cli_prompt(value: str, *, allow_argv: bool) -> str:
    """Resolve a CLI prompt, requiring explicit consent for argv prompts."""
    if value == "-":
        return sys.stdin.read()
    if not allow_argv:
        typer.echo(ARGV_PROMPT_ERROR, err=True)
        raise typer.Exit(2)
    typer.echo(ARGV_PROMPT_WARNING, err=True)
    return value
