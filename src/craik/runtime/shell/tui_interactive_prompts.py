"""Textual bridge for metadata-backed Typer interactive prompts."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, cast

from textual.screen import ModalScreen

from craik.runtime.contract.dispatch import InteractivePromptRequest
from craik.runtime.shell.modals.registry import canonical_modal_registry


def open_interactive_prompt_modal(
    app: Any,
    request: InteractivePromptRequest,
) -> object:
    """Push a canonical modal for an intercepted prompt and wait for completion."""
    modal_class = canonical_modal_registry().get(request.modal_name)
    modal_request = _modal_request_for_interactive_prompt(request)
    if modal_class is None or modal_request is None:
        return _fallback_value(request)

    result_holder: list[object] = []
    event = threading.Event()

    def on_complete(value: object) -> None:
        result_holder.append(value)
        event.set()

    modal_factory = cast(Callable[[object], ModalScreen[Any]], modal_class)
    app.call_from_thread(app.push_screen, modal_factory(modal_request), on_complete)
    event.wait(timeout=300)
    if result_holder:
        return result_holder[0]
    return _fallback_value(request)


def _modal_request_for_interactive_prompt(
    request: InteractivePromptRequest,
) -> object | None:
    if request.modal_name == "ConfirmModal":
        from craik.runtime.shell.modals.confirm import ConfirmRequest

        return ConfirmRequest(
            title=request.prompt_name.replace("_", " ").title(),
            message=request.text,
            destructive=False,
        )
    if request.modal_name == "TextInputModal":
        from craik.runtime.shell.modals.text_input import TextInputRequest

        return TextInputRequest(
            title=request.prompt_name.replace("_", " ").title(),
            message=request.text,
            masked=request.hide_input,
            required=request.default is None,
            initial_value="" if request.default is None else str(request.default),
        )
    return None


def _fallback_value(request: InteractivePromptRequest) -> object:
    return request.default if request.kind == "confirm" else ""
