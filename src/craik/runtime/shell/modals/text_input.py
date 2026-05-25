"""Reusable single-line input modal for CLI/TUI command flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


@dataclass(frozen=True, slots=True)
class TextInputRequest:
    """Configuration for one single-line input prompt."""

    title: str
    message: str
    placeholder: str = ""
    initial_value: str = ""
    submit_label: str = "Submit"
    masked: bool = False
    required: bool = True


class TextInputModal(ModalScreen[str | None]):
    """Collect one line of operator input."""

    supports_masked_input: ClassVar[bool] = True

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "submit", "Submit"),
    ]

    def __init__(self, request: TextInputRequest) -> None:
        super().__init__()
        self.request = request

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(self.request.title, classes="modal-title"),
            Static(self.request.message, classes="modal-copy"),
            Input(
                value=self.request.initial_value,
                placeholder=self.request.placeholder,
                password=self.request.masked,
                id="text-input",
            ),
            Horizontal(
                Button("Cancel", id="text-cancel"),
                Button(self.request.submit_label, id="text-submit", variant="primary"),
                classes="modal-actions",
            ),
            id="text-input-modal",
            classes="craik-modal",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "text-cancel":
            self.dismiss(None)
            return
        if event.button.id == "text-submit":
            self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "text-input":
            self._submit()

    def action_submit(self) -> None:
        self._submit()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        value = self.query_one("#text-input", Input).value
        if self.request.required and not value.strip():
            return
        self.dismiss(value)
