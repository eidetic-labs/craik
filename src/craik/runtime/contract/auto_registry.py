"""auto_registry: derive SlashCommandSpec entries from a Typer app."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import typer

from craik.runtime.contract.craik_command import (
    CRAIK_COMMAND_METADATA_ATTR,
    CraikCommandMetadata,
)
from craik.runtime.shell.slash_command_schema import SlashCommandSpec


@dataclass(frozen=True, slots=True)
class CommandInventoryEntry:
    """One entry in the full command inventory: slash, exempt, or undecorated."""

    command_name: str
    is_slash: bool
    slash_name: str | None
    exempt_reason: str | None
    metadata: CraikCommandMetadata | None
    callback: Callable[..., Any] | None = None


def _iter_typer_commands(app: typer.Typer, prefix: str = "") -> list[tuple[str, Any]]:
    """Walk a Typer app and sub-apps yielding (full command name, callback)."""
    found: list[tuple[str, Any]] = []
    for cmd_info in app.registered_commands:
        if cmd_info.callback is None:
            continue
        name = cmd_info.name or cmd_info.callback.__name__.replace("_", "-")
        full_name = f"{prefix} {name}" if prefix else name
        found.append((full_name, cmd_info.callback))
    for sub_info in app.registered_groups:
        if sub_info.typer_instance is None:
            continue
        name = sub_info.name or (
            sub_info.callback.__name__.replace("_", "-")
            if sub_info.callback is not None
            else ""
        )
        if not name:
            continue
        sub_prefix = f"{prefix} {name}" if prefix else name
        found.extend(_iter_typer_commands(sub_info.typer_instance, sub_prefix))
    return found


def _summary_for(callback: Any, fallback: str) -> str:
    doc = getattr(callback, "__doc__", None)
    if not isinstance(doc, str) or not doc:
        return fallback
    return doc.strip().split("\n", 1)[0]


def _slash_name_for(command_name: str, metadata: CraikCommandMetadata) -> str:
    name = metadata.slash_alias or command_name.replace(" ", "-")
    return f"/{name}"


def derive_slash_specs(app: typer.Typer) -> list[SlashCommandSpec]:
    """Produce SlashCommandSpec entries for decorated TUI-eligible commands."""
    specs: list[SlashCommandSpec] = []
    for full_name, callback in _iter_typer_commands(app):
        metadata: CraikCommandMetadata | None = getattr(
            callback,
            CRAIK_COMMAND_METADATA_ATTR,
            None,
        )
        if metadata is None or not metadata.tui_eligible:
            continue
        slash_name = _slash_name_for(full_name, metadata)
        summary = _summary_for(callback, full_name)
        specs.append(
            SlashCommandSpec(
                name=slash_name,
                summary=summary,
                usage=slash_name,
                payload_shape=metadata.payload_shape,
                help=summary,
                cli_mirror=full_name,
            )
        )
    return specs


@dataclass(frozen=True, slots=True)
class AutoSlashRegistry:
    """Derived slash registry plus full command inventory."""

    slash_specs: tuple[SlashCommandSpec, ...]
    inventory: tuple[CommandInventoryEntry, ...]

    @classmethod
    def from_typer(cls, app: typer.Typer) -> AutoSlashRegistry:
        specs = derive_slash_specs(app)
        inventory: list[CommandInventoryEntry] = []
        for full_name, callback in _iter_typer_commands(app):
            metadata: CraikCommandMetadata | None = getattr(
                callback,
                CRAIK_COMMAND_METADATA_ATTR,
                None,
            )
            if metadata is None:
                inventory.append(
                    CommandInventoryEntry(
                        command_name=full_name,
                        is_slash=False,
                        slash_name=None,
                        exempt_reason=None,
                        metadata=None,
                        callback=callback,
                    )
                )
                continue
            slash_name = _slash_name_for(full_name, metadata) if metadata.tui_eligible else None
            inventory.append(
                CommandInventoryEntry(
                    command_name=full_name,
                    is_slash=metadata.tui_eligible,
                    slash_name=slash_name,
                    exempt_reason=metadata.tui_exempt_reason,
                    metadata=metadata,
                    callback=callback,
                )
            )
        return cls(slash_specs=tuple(specs), inventory=tuple(inventory))

    def spec_by_name(self, slash_name: str) -> SlashCommandSpec | None:
        for spec in self.slash_specs:
            if spec.name == slash_name:
                return spec
        return None

    def all_commands_including_exempt(self) -> tuple[CommandInventoryEntry, ...]:
        return self.inventory

    def undecorated_command_names(self) -> list[str]:
        return [entry.command_name for entry in self.inventory if entry.metadata is None]
