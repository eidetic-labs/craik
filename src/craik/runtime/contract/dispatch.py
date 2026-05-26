"""Unified slash dispatcher for @craik_command callbacks."""

from __future__ import annotations

import io
import os
import shlex
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stdout
from dataclasses import replace
from inspect import Parameter, signature

from craik.runtime.contract.auto_registry import AutoSlashRegistry, CommandInventoryEntry
from craik.runtime.contract.command_result import CommandResult
from craik.runtime.contract.format import format_command_result
from craik.runtime.contract.output_context import slash_dispatch_context
from craik.runtime.shell.contract_runtime.builtin_slash_commands import unknown_command_result
from craik.runtime.shell.slash_command_schema import slash_command_spec_by_name
from craik.runtime.shell.slash_command_schema.help import argument_help_markdown

_INVOCATION_COUNTER = {"count": 0}


def _bump_invocation_counter() -> None:
    """Increment test-observable dispatcher invocation count."""
    _INVOCATION_COUNTER["count"] += 1


def get_invocation_count() -> int:
    """Return how many times contract slash dispatch has been invoked."""
    return _INVOCATION_COUNTER["count"]


def invoke_slash_command(
    text: str,
    *,
    registry: AutoSlashRegistry,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Resolve slash text through a registry and invoke the decorated callback."""
    _bump_invocation_counter()
    tokens = shlex.split(text.strip())
    if not tokens or not tokens[0].startswith("/"):
        return _error_result("slash commands must start with /")
    if tokens[0] == "/craik":
        return _craik_prefix_recovery(tokens)

    entry, args = _resolve_entry(registry, tokens)
    if entry is None or entry.callback is None:
        return unknown_command_result(text, registry)
    if _missing_required_args(entry, args):
        return _argument_help_result(tokens)

    with _patched_environ(env), slash_dispatch_context(), redirect_stdout(io.StringIO()):
        result = _call_entry(entry, args, env=env)
    if isinstance(result, CommandResult):
        command_name = entry.slash_name.removeprefix("/") if entry.slash_name else None
        return (
            result
            if result.command_name is not None
            else replace(result, command_name=command_name)
        )
    return CommandResult(payload=result)


def dispatch_slash_command(
    text: str,
    *,
    registry: AutoSlashRegistry,
    env: dict[str, str] | None = None,
) -> object:
    """Invoke slash text and return the TUI renderer output."""
    result = invoke_slash_command(text, registry=registry, env=env)
    return format_command_result(result, kind="tui")


def _resolve_entry(
    registry: AutoSlashRegistry,
    tokens: list[str],
) -> tuple[CommandInventoryEntry | None, list[str]]:
    grouped_entry = _entry_for_name(registry, tokens[0])
    if grouped_entry is not None and tokens[0] in {
        "/auth",
        "/provider",
        "/model",
        "/receipts",
        "/approvals",
        "/gateway",
        "/agent",
        "/session",
        "/policy",
        "/migrate",
    }:
        return grouped_entry, tokens[1:]
    for split_at in range(min(len(tokens), 4), 0, -1):
        command_name = "-".join(
            part.removeprefix("/") if index == 0 else part
            for index, part in enumerate(tokens[:split_at])
        )
        entry = _entry_for_name(registry, f"/{command_name}")
        if entry is not None:
            return entry, tokens[split_at:]
    return None, []


def _entry_for_name(registry: AutoSlashRegistry, slash_name: str) -> CommandInventoryEntry | None:
    normalized = slash_name if slash_name.startswith("/") else f"/{slash_name}"
    for entry in registry.all_commands_including_exempt():
        if entry.is_slash and entry.slash_name == normalized:
            return entry
    return None


def _call_entry(
    entry: CommandInventoryEntry,
    args: list[str],
    *,
    env: dict[str, str] | None,
) -> object:
    callback = entry.callback
    if callback is None:
        return _error_result(f"unknown slash command: {entry.slash_name or entry.command_name}")
    params = signature(callback).parameters
    try:
        if "env" in params and params["env"].kind in {
            Parameter.KEYWORD_ONLY,
            Parameter.POSITIONAL_OR_KEYWORD,
        }:
            return callback(*args, env=env)
        return callback(*args)
    except Exception as error:
        error_text = str(error)
        return CommandResult(
            payload=error_text,
            shape="markdown",
            text=error_text,
            exit_code=2,
        )


def _missing_required_args(entry: CommandInventoryEntry, args: list[str]) -> bool:
    callback = entry.callback
    if callback is None:
        return False
    required = [
        parameter
        for parameter in signature(callback).parameters.values()
        if parameter.default is Parameter.empty
        and parameter.kind
        in {Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD}
    ]
    return len(args) < len(required)


def _argument_help_result(tokens: list[str]) -> CommandResult:
    topic = tokens[0].removeprefix("/") if tokens else ""
    spec = slash_command_spec_by_name(topic)
    if spec is None and len(tokens) > 1:
        spec = slash_command_spec_by_name(
            "-".join(part.removeprefix("/") for part in tokens[:2])
        )
    text = argument_help_markdown(spec) if spec is not None else f"{topic} requires arguments"
    return CommandResult(
        payload=text,
        shape="markdown",
        text=text,
        exit_code=2,
        command_name="help",
    )


def _craik_prefix_recovery(tokens: list[str]) -> CommandResult:
    if len(tokens) == 1:
        text = "Drop the `craik` prefix. `/help` lists all slash commands."
    else:
        rest = " ".join(tokens[1:])
        text = f"Drop the `craik` prefix — try `/{rest}` instead. `/help` lists all slash commands."
    return CommandResult(payload=text, shape="markdown", text=text)


@contextmanager
def _patched_environ(env: dict[str, str] | None) -> Iterator[None]:
    if env is None:
        yield
        return
    old = os.environ.copy()
    os.environ.update(env)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(old)


def _error_result(message: str) -> CommandResult:
    return CommandResult(
        payload={"error": message},
        shape="kv",
        text=message,
        exit_code=2,
    )
