"""Schema metadata for v0.12.8 new slash commands."""

from __future__ import annotations

from typing import Any


def new_command_specs(
    *,
    spec_cls: Any,
    empty_state_cls: Any,
    named_arg_cls: Any,
) -> tuple[Any, ...]:
    """Return command specs introduced through the v0.12.8 CLI/TUI contract work."""
    return (
        spec_cls(
            name="/cost",
            summary="Show provider cost and token usage.",
            usage="/cost",
            payload_shape="kv",
            help="Show provider token usage, known costs, and explicit accounting gaps.",
            example="/cost",
            empty_state=empty_state_cls(message="No provider usage receipts found."),
        ),
        spec_cls(
            name="/quota",
            summary="Show provider quota state.",
            usage="/quota",
            payload_shape="table",
            help="Show configured provider quota references and runtime quota availability.",
            example="/quota",
            empty_state=empty_state_cls(message="No provider quota metadata found."),
        ),
        spec_cls(
            name="/who",
            summary="Show active operator identity.",
            usage="/who",
            payload_shape="kv",
            help="Show active operator identity and auth profile visibility scope.",
            example="/who",
            empty_state=empty_state_cls(message="No operator session is active."),
        ),
        spec_cls(
            name="/note",
            summary="Add an operator note.",
            usage="/note <text>",
            payload_shape="kv",
            help="Persist an operator note against the active session transcript.",
            example="/note Follow up on release checklist",
            mutating=True,
            args_schema=named_arg_cls,
            required_args=("text",),
            empty_state=empty_state_cls(message="No note text has been provided."),
        ),
        spec_cls(
            name="/fork",
            summary="Fork the active session.",
            usage="/fork",
            payload_shape="kv",
            help="Create a persistent fork of the active session and make it active.",
            example="/fork",
            mutating=True,
            empty_state=empty_state_cls(message="No active session fork is pending."),
        ),
        spec_cls(
            name="/attach",
            summary="Attach a file to session context.",
            usage="/attach <path>",
            payload_shape="kv",
            help="Attach a local file reference to the active session context.",
            example="/attach notes.md",
            mutating=True,
            args_schema=named_arg_cls,
            required_args=("path",),
            empty_state=empty_state_cls(message="No attachment path has been provided."),
        ),
        spec_cls(
            name="/redo",
            summary="Redo the latest agent turn.",
            usage="/redo",
            payload_shape="kv",
            help="Request replay of the latest replayable agent turn.",
            example="/redo",
            mutating=True,
            empty_state=empty_state_cls(message="No replayable agent turn is available."),
        ),
        spec_cls(
            name="/compact",
            summary="Compact the current conversation.",
            usage="/compact",
            payload_shape="kv",
            help="Show the registered placeholder for manual conversation compression.",
            empty_state=empty_state_cls(message="Conversation compression is not implemented yet."),
        ),
        spec_cls(
            name="/share",
            summary="Share the current transcript.",
            usage="/share",
            payload_shape="kv",
            help="Show the registered placeholder for public transcript sharing.",
            empty_state=empty_state_cls(message="Transcript sharing is not implemented yet."),
        ),
    )
