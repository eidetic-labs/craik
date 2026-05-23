from __future__ import annotations

from craik.runtime.shell.textual_widgets.action_marker import (
    ActionMarkerData,
    render_action_marker,
)


def test_action_marker_renders_receipt_link_text() -> None:
    marker = ActionMarkerData("approved", "Auto-reviewer approved file read", "receipt_1")

    assert render_action_marker(marker) == "✓ Auto-reviewer approved file read (receipt_1)"
