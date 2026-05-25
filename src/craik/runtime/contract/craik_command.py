"""@craik_command decorator: capture TUI metadata for Typer commands."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar, get_args

from craik.runtime.contract.command_result import PayloadShape

CRAIK_COMMAND_METADATA_ATTR = "__craik_command_metadata__"

_LEGAL_SHAPES = set(get_args(PayloadShape))

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True, slots=True)
class CraikCommandMetadata:
    """Metadata captured by @craik_command for a Typer command."""

    tui_eligible: bool = True
    slash_alias: str | None = None
    payload_shape: PayloadShape = "auto"
    interactive_prompts: dict[str, str] = field(default_factory=dict)
    tui_exempt_reason: str | None = None


def craik_command(
    *,
    tui_eligible: bool = True,
    slash_alias: str | None = None,
    payload_shape: PayloadShape = "auto",
    interactive_prompts: dict[str, str] | None = None,
    tui_exempt_reason: str | None = None,
) -> Callable[[F], F]:
    """Decorator capturing TUI-relevant metadata on a Typer command function."""
    if not tui_eligible and not tui_exempt_reason:
        raise ValueError(
            "tui_eligible=False requires a tui_exempt_reason explaining "
            "why this command stays CLI-only. Example: tui_exempt_reason="
            "'streams unbounded stdin; only useful in pipe context'"
        )
    if payload_shape not in _LEGAL_SHAPES:
        raise ValueError(
            f"payload_shape={payload_shape!r} is not a legal PayloadShape. "
            f"Legal values: {sorted(_LEGAL_SHAPES)}"
        )

    metadata = CraikCommandMetadata(
        tui_eligible=tui_eligible,
        slash_alias=slash_alias,
        payload_shape=payload_shape,
        interactive_prompts=dict(interactive_prompts or {}),
        tui_exempt_reason=tui_exempt_reason,
    )

    def _wrap(func: F) -> F:
        setattr(func, CRAIK_COMMAND_METADATA_ATTR, metadata)
        return func

    return _wrap
