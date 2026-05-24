"""Command-name mistype suggestions for Typer command groups."""

from __future__ import annotations

from collections.abc import Iterable

import click
from click.parser import split_opt
from typer.core import TyperGroup

MAX_COMMAND_DISTANCE = 2


class SuggestingTyperGroup(TyperGroup):
    """Typer group that appends close command suggestions to usage errors."""

    def resolve_command(
        self,
        ctx: click.Context,
        args: list[str],
    ) -> tuple[str | None, click.Command | None, list[str]]:
        command_name = click.utils.make_str(args[0])
        original_name = command_name
        command = self.get_command(ctx, command_name)
        if command is None and ctx.token_normalize_func is not None:
            command_name = ctx.token_normalize_func(command_name)
            command = self.get_command(ctx, command_name)
        if command is None and not ctx.resilient_parsing:
            if split_opt(command_name)[0]:
                self.parse_args(ctx, ctx.args)
            message = f"No such command {original_name!r}."
            if suggestion := closest_command(original_name, self.commands):
                message = f"{message} Did you mean '{_command_path(ctx, suggestion)}'?"
            ctx.fail(message)
        return command_name if command else None, command, args[1:]


def closest_command(
    value: str,
    candidates: Iterable[str],
    *,
    max_distance: int = MAX_COMMAND_DISTANCE,
) -> str | None:
    """Return the closest command candidate within the edit-distance threshold."""
    ranked = sorted(
        (_levenshtein(value, candidate), candidate)
        for candidate in candidates
        if not candidate.startswith("_")
    )
    if not ranked:
        return None
    distance, candidate = ranked[0]
    return candidate if distance <= max_distance else None


def _command_path(ctx: click.Context, suggestion: str) -> str:
    tokens = ctx.command_path.split()
    if not tokens:
        return f"craik {suggestion}"
    tokens[0] = "craik"
    return " ".join([*tokens, suggestion])


def _levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, start=1):
        current = [row]
        for column, right_char in enumerate(right, start=1):
            substitution = previous[column - 1] + (left_char != right_char)
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    substitution,
                )
            )
        previous = current
    return previous[-1]
