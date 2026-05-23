from __future__ import annotations

from craik.runtime.shell.textual_widgets.collapsible_log import collapsible_log_text


def test_collapsible_log_collapses_after_threshold() -> None:
    text = "one\ntwo\nthree\nfour"

    assert collapsible_log_text(text) == "one\ntwo\n… +2 lines"
    assert collapsible_log_text(text, expanded=True) == text
