"""Tests for the adapter seam foundation: `RunContext` + `Adapter` protocol."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable

import pytest

from craik.runtime.backend.adapters.base import Adapter, RunContext
from craik.runtime.backend.events import BackendEvent, assistant_text_event


class FakeAdapter:
    """A trivial adapter satisfying the structural `Adapter` protocol."""

    vendor = "anthropic"
    surface = "cli"

    def supports_live_gating(self) -> bool:
        return True

    def run(self, ctx: RunContext) -> Iterable[BackendEvent]:
        yield assistant_text_event(text="hi", source="anthropic-cli", run_id="r")


def _ctx() -> RunContext:
    return RunContext(
        prompt="hello",
        env={},
        emit=lambda event: None,
        decide=lambda request: "allow",
        require_operator_approval=False,
    )


def test_run_context_carries_all_fields() -> None:
    ctx = _ctx()
    assert ctx.prompt == "hello"
    assert ctx.env == {}
    assert callable(ctx.emit)
    assert callable(ctx.decide)
    assert ctx.require_operator_approval is False


def test_run_context_is_frozen() -> None:
    ctx = _ctx()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.prompt = "mutated"  # type: ignore[misc]


def test_fake_adapter_run_yields_one_assistant_text_event() -> None:
    # A type-level assertion that FakeAdapter satisfies the structural protocol;
    # mypy verifies this, and there is no explicit inheritance.
    adapter: Adapter = FakeAdapter()

    events = list(adapter.run(_ctx()))

    assert len(events) == 1
    (event,) = events
    assert isinstance(event, BackendEvent)
    assert event.type == "assistant_text"
