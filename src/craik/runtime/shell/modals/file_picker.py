"""Reusable file-picker modal for CLI/TUI command flows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


@dataclass(frozen=True, slots=True)
class FilePickerRequest:
    """Configuration for a path selection prompt."""

    title: str
    message: str
    base_path: Path
    initial_value: str = ""
    submit_label: str = "Attach"
    must_exist: bool = True


class FilePickerModal(ModalScreen[Path | None]):
    """Collect one operator-selected file path."""

    supports_masked_input: ClassVar[bool] = False

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "submit", "Submit"),
    ]

    def __init__(self, request: FilePickerRequest) -> None:
        super().__init__()
        self.request = request

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(self.request.title, classes="modal-title"),
            Static(self.request.message, classes="modal-copy"),
            Static(f"Base: {self.request.base_path}", classes="modal-copy"),
            Input(
                value=self.request.initial_value,
                placeholder="relative/path.txt",
                id="file-path",
            ),
            Horizontal(
                Button("Cancel", id="file-cancel"),
                Button(self.request.submit_label, id="file-submit", variant="primary"),
                classes="modal-actions",
            ),
            id="file-picker-modal",
            classes="craik-modal",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "file-cancel":
            self.dismiss(None)
            return
        if event.button.id == "file-submit":
            self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "file-path":
            self._submit()

    def action_submit(self) -> None:
        self._submit()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        raw_path = self.query_one("#file-path", Input).value.strip()
        if not raw_path:
            return
        candidate = (self.request.base_path / raw_path).resolve()
        if self.request.must_exist and not candidate.is_file():
            return
        self.dismiss(candidate)
