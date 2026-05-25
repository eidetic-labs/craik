"""Tests for the @craik_command decorator."""

from __future__ import annotations

import pytest

from craik.runtime.contract import CommandResult
from craik.runtime.contract.craik_command import (
    CRAIK_COMMAND_METADATA_ATTR,
    CraikCommandMetadata,
    craik_command,
)


def test_decorator_attaches_default_metadata() -> None:
    @craik_command()
    def my_command() -> CommandResult:
        return CommandResult(payload={})

    metadata = getattr(my_command, CRAIK_COMMAND_METADATA_ATTR)
    assert isinstance(metadata, CraikCommandMetadata)
    assert metadata.tui_eligible is True
    assert metadata.slash_alias is None
    assert metadata.payload_shape == "auto"
    assert metadata.interactive_prompts == {}
    assert metadata.tui_exempt_reason is None


def test_decorator_with_explicit_metadata() -> None:
    @craik_command(
        tui_eligible=True,
        slash_alias="settings",
        payload_shape="kv",
        interactive_prompts={"provider_name": "select_provider_modal"},
    )
    def setup_command() -> CommandResult:
        return CommandResult(payload={})

    metadata = getattr(setup_command, CRAIK_COMMAND_METADATA_ATTR)
    assert metadata.slash_alias == "settings"
    assert metadata.payload_shape == "kv"
    assert metadata.interactive_prompts == {"provider_name": "select_provider_modal"}


def test_decorator_tui_exempt_requires_reason() -> None:
    with pytest.raises(ValueError, match="tui_exempt_reason"):

        @craik_command(tui_eligible=False)
        def cmd() -> CommandResult:
            return CommandResult(payload={})


def test_decorator_tui_exempt_with_reason() -> None:
    @craik_command(
        tui_eligible=False,
        tui_exempt_reason="streams unbounded stdin; only useful in pipe context",
    )
    def cmd() -> CommandResult:
        return CommandResult(payload={})

    metadata = getattr(cmd, CRAIK_COMMAND_METADATA_ATTR)
    assert metadata.tui_eligible is False
    assert metadata.tui_exempt_reason is not None


def test_decorator_preserves_function_identity() -> None:
    @craik_command()
    def my_cmd() -> CommandResult:
        """Original docstring."""
        return CommandResult(payload={"original": True})

    result = my_cmd()
    assert result.payload == {"original": True}
    assert my_cmd.__name__ == "my_cmd"
    assert my_cmd.__doc__ == "Original docstring."


def test_decorator_rejects_invalid_shape() -> None:
    with pytest.raises(ValueError, match="payload_shape"):

        @craik_command(payload_shape="bogus")  # type: ignore[arg-type]
        def cmd() -> CommandResult:
            return CommandResult(payload={})
