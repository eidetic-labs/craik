"""Detailed help rendering for registered slash commands."""

from __future__ import annotations

import difflib
from collections.abc import Iterable
from typing import Any

from craik.runtime.i18n import text as localized_text
from craik.runtime.shell.slash_command_schema import (
    ActionKeySet,
    SlashCommandSpec,
)
from craik.runtime.shell.slash_command_schema.lookup import (
    find_slash_command_spec,
    slash_command_names,
)


def command_detail_help(
    name: str,
    *,
    env: dict[str, str] | None = None,
    specs: Iterable[SlashCommandSpec] | None = None,
) -> str:
    """Render a full Markdown help page for one slash command."""
    normalized = name.removeprefix("/")
    if specs is None:
        from craik.runtime.shell.contract_runtime.registry_provider import get_tui_slash_specs

        spec_list = get_tui_slash_specs()
    else:
        spec_list = tuple(specs)
    spec = find_slash_command_spec(spec_list, normalized)
    if spec is None:
        suggestion = _suggest(normalized, spec_list)
        suffix = f" Did you mean `{suggestion}`?" if suggestion else ""
        return f"No such slash command: `/{normalized}`.{suffix}"
    lines = [
        f"## {spec.name}",
        "",
        spec.help,
        "",
        f"- {localized_text('slash.help.usage', env=env)}: {spec.usage}",
        f"- Output: `{spec.payload_shape}`",
        f"- {localized_text('slash.help.requires', env=env)}: {spec.readiness}",
    ]
    if spec.required_args:
        lines.append("- Required arguments: " + ", ".join(f"`{arg}`" for arg in spec.required_args))
    if spec.choices:
        for arg, choices in spec.choices.items():
            lines.append(f"- `{arg}` choices: " + ", ".join(f"`{choice}`" for choice in choices))
    examples = tuple(
        dict.fromkeys(example for example in (*spec.examples, spec.example) if example)
    )
    if examples:
        lines.append("- Examples: " + ", ".join(f"`{example}`" for example in examples))
    actions = _action_key_help(spec.action_keys)
    if actions:
        lines.append("- Action keys: " + actions)
    if spec.requires_confirmation:
        message = f" {spec.confirm_message}" if spec.confirm_message else ""
        lines.append(f"- Confirmation: required.{message}")
    return "\n".join(lines)


def _action_key_help(action_keys: ActionKeySet) -> str:
    values: dict[str, Any] = action_keys.model_dump(exclude_none=True, by_alias=True)
    return " · ".join(f"`{key}`={value}" for key, value in values.items())


def _suggest(name: str, specs: Iterable[SlashCommandSpec]) -> str | None:
    matches = difflib.get_close_matches(
        name,
        slash_command_names(specs),
        n=1,
        cutoff=0.65,
    )
    return f"/{matches[0]}" if matches else None
