"""CLI-TUI contract: shared command result types."""

from craik.runtime.contract.command_result import CommandResult, NextAction, PayloadShape
from craik.runtime.contract.craik_command import (
    CRAIK_COMMAND_METADATA_ATTR,
    CraikCommandMetadata,
    craik_command,
)

__all__ = [
    "CRAIK_COMMAND_METADATA_ATTR",
    "CommandResult",
    "CraikCommandMetadata",
    "NextAction",
    "PayloadShape",
    "craik_command",
]
