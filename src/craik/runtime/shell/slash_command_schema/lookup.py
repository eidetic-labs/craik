"""Lookup helpers for registry-derived slash command specs."""

from __future__ import annotations

from collections.abc import Iterable

from craik.runtime.shell.slash_command_schema import SlashCommandSpec


def find_slash_command_spec(
    specs: Iterable[SlashCommandSpec],
    name: str,
) -> SlashCommandSpec | None:
    """Return the command spec for a slash-prefixed or bare command name."""
    normalized = name.strip().removeprefix("/")
    for spec in specs:
        if spec.command_name == normalized or normalized in spec.aliases:
            return spec
    return None


def slash_command_names(
    specs: Iterable[SlashCommandSpec],
    *,
    include_aliases: bool = True,
) -> list[str]:
    """Return slash command names without slash prefixes."""
    values: list[str] = []
    for spec in specs:
        values.append(spec.command_name)
        if include_aliases:
            values.extend(spec.aliases)
    return values
