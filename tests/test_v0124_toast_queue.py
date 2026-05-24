from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult

from craik.runtime.shell.textual_widgets.toast_queue import (
    MAX_VISIBLE_TOASTS,
    TOAST_TIMEOUTS,
    ToastNotice,
    ToastQueue,
    render_toast_queue,
)


def test_toast_timeouts_per_severity_defaults() -> None:
    assert TOAST_TIMEOUTS["information"] == 3
    assert TOAST_TIMEOUTS["warning"] == 8
    assert TOAST_TIMEOUTS["error"] is None


def test_render_toast_queue_escapes_adversarial_markup_in_message() -> None:
    rendered = render_toast_queue(
        [ToastNotice(message="[red blink]injection[/red blink]", severity="information")]
    )

    assert "\\[red blink]" in rendered
    assert ": [red blink]" not in rendered


def test_render_toast_queue_includes_escaped_severity() -> None:
    rendered = render_toast_queue([ToastNotice(message="hello", severity="information")])

    assert "information" in rendered


def test_render_toast_queue_caps_visible_notices() -> None:
    notices = [
        ToastNotice(message=f"toast-{index}", severity="information")
        for index in range(MAX_VISIBLE_TOASTS + 2)
    ]

    rendered = render_toast_queue(notices[-MAX_VISIBLE_TOASTS:])

    assert rendered.count("toast-") == MAX_VISIBLE_TOASTS
    assert "toast-0" not in rendered


def test_toast_queue_auto_dismisses_information_after_timeout() -> None:
    async def run() -> None:
        async with _ToastHost().run_test() as pilot:
            queue = pilot.app.query_one(ToastQueue)
            queue.push("hello", severity="information")
            assert len(queue.notices) == 1

            await pilot.pause((TOAST_TIMEOUTS["information"] or 0) + 0.25)

            assert queue.notices == []
            assert queue.display is False

    asyncio.run(run())


def test_toast_queue_does_not_auto_dismiss_error_severity() -> None:
    async def run() -> None:
        async with _ToastHost().run_test() as pilot:
            queue = pilot.app.query_one(ToastQueue)
            queue.push("danger", severity="error")

            await pilot.pause(0.25)

            assert len(queue.notices) == 1
            queue.dismiss()
            assert queue.notices == []

    asyncio.run(run())


class _ToastHost(App[None]):
    def compose(self) -> ComposeResult:
        yield ToastQueue(id="toast-queue")
