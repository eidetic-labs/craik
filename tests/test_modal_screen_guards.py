"""Coverage for v0.12.8 modal metadata guards."""

from __future__ import annotations

import typer

from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.shell.modals import (
    ConfirmModal,
    FilePickerModal,
    MultilineInputModal,
    SelectChoiceModal,
    TextInputModal,
    canonical_modal_registry,
    modal_supports_secret_capture,
    resolve_modal_class,
)
from craik.runtime.shell.modals.guards import modal_mapping_failures, modal_security_failures


def test_canonical_modal_registry_resolves_required_classes() -> None:
    registry = canonical_modal_registry()

    canonical_names = {name for name in registry if name.endswith("Modal")}
    assert canonical_names == {
        "ConfirmModal",
        "FilePickerModal",
        "MultilineInputModal",
        "SelectChoiceModal",
        "TextInputModal",
    }
    assert resolve_modal_class("ConfirmModal", registry) is ConfirmModal
    assert resolve_modal_class("text_input", registry) is TextInputModal
    assert resolve_modal_class("select_choice", registry) is SelectChoiceModal
    assert resolve_modal_class("multiline_input", registry) is MultilineInputModal
    assert resolve_modal_class("file_picker", registry) is FilePickerModal


def test_only_text_input_modal_supports_secret_capture() -> None:
    assert modal_supports_secret_capture(TextInputModal) is True
    assert modal_supports_secret_capture(ConfirmModal) is False


def test_modal_mapping_guard_rejects_unknown_target() -> None:
    app = typer.Typer()

    @app.command("login")
    @craik_command(interactive_prompts={"provider": "UnknownModal"})
    def login() -> CommandResult:
        return CommandResult(payload={"ok": True}, shape="kv")

    failures = modal_mapping_failures(AutoSlashRegistry.from_typer(app))

    assert failures == ["login: 'provider' references unknown modal 'UnknownModal'"]


def test_modal_mapping_guard_accepts_canonical_target() -> None:
    app = typer.Typer()

    @app.command("login")
    @craik_command(interactive_prompts={"provider": "SelectChoiceModal"})
    def login() -> CommandResult:
        return CommandResult(payload={"ok": True}, shape="kv")

    assert modal_mapping_failures(AutoSlashRegistry.from_typer(app)) == []


def test_current_prompt_backed_commands_declare_modal_metadata() -> None:
    from craik.cli import app

    registry = AutoSlashRegistry.from_typer(app)
    prompts_by_command = {
        entry.command_name: entry.metadata.interactive_prompts
        for entry in registry.inventory
        if entry.metadata is not None
    }

    assert prompts_by_command["auth login"] == {"reauthenticate": "ConfirmModal"}
    assert prompts_by_command["migrate import"] == {"apply_import": "ConfirmModal"}


def test_modal_security_guard_rejects_sensitive_prompt_without_masked_input() -> None:
    app = typer.Typer()

    @app.command("login")
    @craik_command(interactive_prompts={"api_key": "ConfirmModal"})
    def login() -> CommandResult:
        return CommandResult(payload={"ok": True}, shape="kv")

    failures = modal_security_failures(AutoSlashRegistry.from_typer(app))

    assert failures == [
        "login: sensitive prompt 'api_key' maps to 'ConfirmModal', "
        "which does not support masked input"
    ]


def test_modal_security_guard_accepts_masked_input_capable_modal() -> None:
    app = typer.Typer()

    @app.command("login")
    @craik_command(interactive_prompts={"api_key": "TextInputModal"})
    def login() -> CommandResult:
        return CommandResult(payload={"ok": True}, shape="kv")

    assert modal_security_failures(AutoSlashRegistry.from_typer(app)) == []
