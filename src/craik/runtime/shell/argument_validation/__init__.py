"""Runtime argument validation for slash-command dispatch."""

from __future__ import annotations

from typing import Protocol

from craik.runtime.shell.slash_command_schema import (
    ModelArgs,
    NamedArg,
    ThemeArgs,
    slash_command_spec_by_name,
)


class SlashCommandSurface(Protocol):
    """Command fields needed for argument validation."""

    @property
    def name(self) -> str:
        """Return the bare slash-command name."""
        ...


def argument_validation_error(command: SlashCommandSurface, args: list[str]) -> str | None:
    """Return operator-facing validation guidance for command args."""
    spec = slash_command_spec_by_name(command.name)
    if spec is None or spec.args_schema is None:
        return None
    if spec.args_schema is ThemeArgs:
        if len(args) > 1:
            return f"`/{command.name}` accepts at most one theme argument. Usage: `{spec.usage}`"
        try:
            ThemeArgs.model_validate({"theme": args[0] if args else None})
        except ValueError:
            choices = ", ".join(f"`{choice}`" for choice in spec.choices.get("theme", ()))
            return f"unknown theme `{args[0]}`. Choose one of: {choices}."
        return None
    if spec.args_schema is ModelArgs:
        action = args[0] if args else None
        selector = args[1] if len(args) > 1 else None
        if len(args) > 2:
            return f"`/{command.name}` received too many arguments. Usage: `{spec.usage}`"
        try:
            ModelArgs.model_validate({"action": action, "selector": selector})
        except ValueError as error:
            return f"invalid /model arguments: {_validation_detail(error)}. Usage: `{spec.usage}`"
        return None
    if spec.args_schema is NamedArg:
        if not args:
            required = ", ".join(spec.required_args)
            return f"`/{command.name}` requires {required}. Usage: `{spec.usage}`"
        NamedArg(value=" ".join(args))
    return None


def _validation_detail(error: ValueError) -> str:
    for line in str(error).splitlines():
        if "Value error," in line:
            return line.split("Value error,", 1)[1].strip()
    return str(error).splitlines()[0]
