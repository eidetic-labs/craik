"""Tests for the streaming assistant-text Coalescer.

Cumulative streaming means each snapshot is the full assistant text-so-far
(often a prefix-extension of the prior). The Coalescer must SUPERSEDE — keep
only the latest snapshot per run — never concatenate.
"""

from __future__ import annotations

from craik.runtime.backend.events import BackendEvent, Coalescer


def test_cumulative_snapshots_supersede_not_append() -> None:
    """Three cumulative snapshots collapse to the latest, not their concat."""
    coalescer = Coalescer()
    for snapshot in ("Yes", "Yes I", "Yes I can"):
        coalescer.update("run1", snapshot)

    assert coalescer.assistant_text("run1") == "Yes I can"


def test_flush_emits_single_first_class_assistant_text_event() -> None:
    """flush returns one assistant_text event carrying the superseding text."""
    coalescer = Coalescer()
    for snapshot in ("Yes", "Yes I", "Yes I can"):
        coalescer.update("run1", snapshot)

    ev = coalescer.flush("run1", source="anthropic-cli")
    assert isinstance(ev, BackendEvent)
    d = ev.as_dict()
    assert d["type"] == "assistant_text"
    assert d["data"] == {"text": "Yes I can"}
    assert d["source"] == "anthropic-cli"
    assert d["run_id"] == "run1"


def test_per_run_isolation() -> None:
    """Snapshots for distinct run_ids coalesce independently."""
    coalescer = Coalescer()
    coalescer.update("run1", "Hello")
    coalescer.update("run2", "Goodbye")
    coalescer.update("run1", "Hello there")

    assert coalescer.assistant_text("run1") == "Hello there"
    assert coalescer.assistant_text("run2") == "Goodbye"


def test_flush_clears_run_state() -> None:
    """After flush the run's text is consumed (subsequent flush is None)."""
    coalescer = Coalescer()
    coalescer.update("run1", "done")

    first = coalescer.flush("run1", source="anthropic-cli")
    assert first is not None
    assert coalescer.assistant_text("run1") is None
    assert coalescer.flush("run1", source="anthropic-cli") is None


def test_flush_with_no_text_returns_none() -> None:
    """flush on a run that never received a snapshot returns None."""
    coalescer = Coalescer()
    assert coalescer.flush("never", source="anthropic-cli") is None
