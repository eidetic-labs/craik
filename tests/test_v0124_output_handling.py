from __future__ import annotations

import asyncio
from pathlib import Path

from rich.console import Console

from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.shell.textual_app import CraikApp
from craik.runtime.shell.textual_widgets.craik_input import CraikInput
from craik.runtime.shell.textual_widgets.slash_renderers import render_slash_payload
from craik.runtime.shell.textual_widgets.toast_queue import (
    MAX_VISIBLE_TOASTS,
    TOAST_TIMEOUTS,
    ToastQueue,
)


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik"), "TERM": "xterm-256color"}


def _render_text(renderable: object) -> str:
    console = Console(record=True, width=120)
    console.print(renderable)
    return console.export_text()


def test_large_table_payload_collapses_with_expand_and_search_hint() -> None:
    renderable = render_slash_payload(
        [{"index": index, "value": f"row-{index}"} for index in range(55)],
        shape="table",
    )

    rendered = _render_text(renderable)

    assert "row-0" in rendered
    assert "row-54" not in rendered
    assert "Space=expand" in rendered
    assert "Ctrl+F=find" in rendered


def test_empty_state_metadata_is_attached_to_empty_session_results(tmp_path: Path) -> None:
    result = dispatch_slash_command("/sessions", env=_env(tmp_path))

    assert result.empty_state_message == "No persistent sessions found."
    assert result.empty_state_remediation is not None
    assert "/resume <session-id>" in result.empty_state_remediation


def test_toast_queue_caps_visible_notices_and_tracks_timeouts() -> None:
    queue = ToastQueue()
    queue.push("one")
    queue.push("two", severity="warning")
    queue.push("three", severity="error")
    queue.push("four")

    assert len(queue.notices) == MAX_VISIBLE_TOASTS
    assert [notice.message for notice in queue.notices] == ["two", "three", "four"]
    assert TOAST_TIMEOUTS["information"] == 3
    assert TOAST_TIMEOUTS["warning"] == 8
    assert TOAST_TIMEOUTS["error"] is None


def test_forgot_slash_uses_visible_toast_queue(tmp_path: Path) -> None:
    async def run() -> None:
        app = CraikApp(env=_env(tmp_path))
        async with app.run_test() as pilot:
            input_widget = app.query_one("#input", CraikInput)
            input_widget.value = "provider"
            await pilot.press("enter")
            queue = app.query_one("#toast-queue", ToastQueue)
            assert queue.display
            assert queue.notices[-1].severity == "warning"
            assert "Did you mean `/provider`" in queue.notices[-1].message

    asyncio.run(run())
