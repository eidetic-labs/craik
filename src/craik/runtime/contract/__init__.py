"""CLI-TUI contract: shared command result types."""

from craik.runtime.contract.command_result import CommandResult, NextAction, PayloadShape
from craik.runtime.contract.craik_command import (
    CRAIK_COMMAND_METADATA_ATTR,
    CraikCommandMetadata,
    craik_command,
)
from craik.runtime.contract.format import FormatKind, detect_default_format, format_command_result
from craik.runtime.contract.output_context import slash_dispatch_active, slash_dispatch_context

__all__ = [
    "CRAIK_COMMAND_METADATA_ATTR",
    "CommandResult",
    "CraikCommandMetadata",
    "FormatKind",
    "NextAction",
    "PayloadShape",
    "craik_command",
    "detect_default_format",
    "format_command_result",
    "slash_dispatch_active",
    "slash_dispatch_context",
]
