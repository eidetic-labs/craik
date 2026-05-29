"""Slash catalog event helpers for Gateway clients."""

from __future__ import annotations

import os

from craik.runtime.modeling import ModelSettingsStore
from craik.runtime.providers.model_providers import default_model_provider_registry
from craik.runtime.shell.contract_runtime.builtin_slash_commands import (
    CLAUDE_PERMISSION_MODE_ENV,
)
from craik.runtime.shell.slash_command_schema import SlashCommandSpec
from craik.runtime.shell.textual_widgets.theme_settings import current_theme


def slash_catalog_entry(
    spec: SlashCommandSpec,
    env: dict[str, str] | None,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "name": spec.command_name,
        "usage": spec.usage,
        "summary": spec.summary,
        "aliases": list(spec.aliases),
        "mutating": spec.mutating,
        "requires_confirmation": spec.requires_confirmation,
    }
    if spec.cli_mirror:
        entry["cli_mirror"] = spec.cli_mirror
    if spec.confirm_message:
        entry["confirm_message"] = spec.confirm_message
    if spec.required_args:
        entry["required_args"] = list(spec.required_args)
    if spec.examples:
        entry["examples"] = list(spec.examples)
    elif spec.example:
        entry["examples"] = [spec.example]
    if spec.choices:
        entry["choices"] = {key: list(values) for key, values in spec.choices.items()}
    if spec.command_name == "model":
        model_choices = _model_catalog_choices(env)
        if model_choices:
            entry["model_choices"] = model_choices
    subcommands = _usage_subcommands(spec.usage)
    if subcommands:
        entry["subcommands"] = subcommands
    current_value = _current_catalog_value(spec.command_name, env)
    if current_value is not None:
        entry["current_value"] = current_value
    return entry


def _model_catalog_choices(env: dict[str, str] | None) -> list[str]:
    settings = ModelSettingsStore.from_env(env).load()
    choices: list[str] = []
    if settings.active_model is not None:
        choices.append(settings.active_model)
    choices.extend(settings.aliases.values())
    choices.extend(settings.fallbacks)
    for profile in settings.profiles.values():
        choices.append(f"{profile.provider_family}/{profile.model}")
    for provider in default_model_provider_registry().list():
        default_model = provider.metadata.get("default_model")
        if isinstance(default_model, str) and default_model.strip():
            choices.append(f"{provider.provider}/{default_model}")
    return _unique_strings(choices)


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _usage_subcommands(usage: str) -> list[str]:
    if "[" not in usage or "]" not in usage:
        return []
    inner = usage.split("[", 1)[1].split("]", 1)[0]
    return [
        token
        for token in inner.replace("|", " ").split()
        if not token.startswith("<")
        and all(character.isalpha() or character == "-" for character in token)
    ]


def _current_catalog_value(command_name: str, env: dict[str, str] | None) -> str | None:
    if command_name == "model":
        return ModelSettingsStore.from_env(env).load().active_model
    if command_name == "mode":
        values = os.environ if env is None else env
        return _display_permission_mode(values.get(CLAUDE_PERMISSION_MODE_ENV, "default"))
    if command_name == "effort":
        profile = ModelSettingsStore.from_env(env).load().active_profile
        if profile is None:
            return None
        effort = profile.options.get("reasoning_effort")
        return effort if isinstance(effort, str) and effort.strip() else "default"
    if command_name == "theme":
        return current_theme(env)
    return None


def _display_permission_mode(mode: str) -> str:
    return "ask" if mode == "default" else mode
