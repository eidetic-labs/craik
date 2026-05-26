"""CommandResult: the universal return type for Craik commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PayloadShape = Literal["auto", "kv", "card", "card_list", "table", "tree", "markdown"]


@dataclass(frozen=True, slots=True)
class NextAction:
    """An inline action affordance rendered next to an actionable field."""

    text: str
    command: str
    field: str | None = None


@dataclass(frozen=True, slots=True)
class CommandResult:
    """The universal return type for command-contract migrated commands."""

    payload: Any
    shape: PayloadShape = "auto"
    text: str | None = None
    exit_code: int = 0
    exit_shell: bool = False
    command_name: str | None = None
    next_actions: list[NextAction] = field(default_factory=list)
    empty_state_message: str | None = None
