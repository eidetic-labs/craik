"""Reusable multiline input modal for CLI/TUI command flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static, TextArea


@dataclass(frozen=True, slots=True)
class MultilineInputRequest:
    """Configuration for one multiline input prompt."""

    title: str
    message: str
    initial_value: str = ""
    submit_label: str = "Submit"
    required: bool = True


class MultilineInputModal(ModalScreen[str | None]):
    """Collect multiline operator input."""

    supports_masked_input: ClassVar[bool] = False

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "submit", "Submit"),
    ]

    def __init__(self, request: MultilineInputRequest) -> None:
        super().__init__()
        self.request = request

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(self.request.title, classes="modal-title"),
            Static(self.request.message, classes="modal-copy"),
            TextArea(self.request.initial_value, id="multiline-input"),
            Horizontal(
                Button("Cancel", id="multiline-cancel"),
                Button(self.request.submit_label, id="multiline-submit", variant="primary"),
                classes="modal-actions",
            ),
            id="multiline-input-modal",
            classes="craik-modal",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "multiline-cancel":
            self.dismiss(None)
            return
        if event.button.id == "multiline-submit":
            self._submit()

    def action_submit(self) -> None:
        self._submit()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        value = self.query_one("#multiline-input", TextArea).text
        if self.request.required and not value.strip():
            return
        self.dismiss(value)
