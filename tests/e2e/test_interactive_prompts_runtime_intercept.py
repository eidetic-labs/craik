"""Verify interactive prompt metadata drives runtime interception."""

from __future__ import annotations

import typer

from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.contract.dispatch import InteractivePromptRequest, invoke_slash_command


def test_interactive_prompt_metadata_intercepts_confirm_call() -> None:
    app = typer.Typer()
    seen: list[InteractivePromptRequest] = []

    @app.command("danger")
    @craik_command(payload_shape="kv", interactive_prompts={"confirm_danger": "ConfirmModal"})
    def danger() -> CommandResult:
        confirmed = typer.confirm("Continue?", default=False)
        return CommandResult(payload={"confirmed": confirmed}, shape="kv")

    def _handler(request: InteractivePromptRequest) -> object:
        seen.append(request)
        return True

    result = invoke_slash_command(
        "/danger",
        registry=AutoSlashRegistry.from_typer(app),
        interactive_prompt_handler=_handler,
    )

    assert result.payload == {"confirmed": True}
    assert seen == [
        InteractivePromptRequest(
            kind="confirm",
            prompt_name="confirm_danger",
            modal_name="ConfirmModal",
            text="Continue?",
            default=False,
        )
    ]
