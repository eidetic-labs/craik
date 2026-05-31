"""Tests for the adapter family bases: ``CLIAdapter`` and ``APIAdapter``.

These bases implement the ``Adapter`` protocol via the template-method pattern.
We exercise them with FAKE subclasses only -- the real per-vendor request /
subprocess / execute code lands in Phase 4. The governance-critical assertion
is that ``APIAdapter`` sends ONLY caller-executed ``type=="function"`` tools and
strips vendor hosted/server-side tools unless an audited opt-out is set.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from craik.runtime.backend.adapters.base import APIAdapter, CLIAdapter, RunContext
from craik.runtime.backend.events import (
    BackendEvent,
    assistant_text_event,
)


def _ctx(
    *,
    decide: Any = None,
    prompt: str = "hello",
) -> RunContext:
    return RunContext(
        prompt=prompt,
        env={"CRAIK_TOKEN": "x"},
        emit=lambda event: None,
        decide=decide or (lambda request: "allow"),
        require_operator_approval=False,
    )


# --- CLIAdapter -------------------------------------------------------------


class FakeCLIAdapter(CLIAdapter):
    """A CLI adapter whose hooks record their invocation order."""

    vendor = "anthropic"
    surface = "cli"

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def build_command(self, ctx: RunContext) -> list[str]:
        self.calls.append("build_command")
        return ["claude", "--prompt", ctx.prompt]

    def spawn(self, cmd: list[str], env: dict[str, str]) -> Iterable[str]:
        self.calls.append("spawn")
        # Two JSON lines + one blank line that parse_stream should skip.
        return ['{"text": "hello"}', "", '{"text": "world"}']

    def map_native_event(self, native: dict[str, Any]) -> BackendEvent | None:
        self.calls.append("map_native_event")
        return assistant_text_event(text=native["text"], source="anthropic-cli")


def test_cli_run_drives_hooks_in_order_and_yields_events() -> None:
    adapter = FakeCLIAdapter()

    events = list(adapter.run(_ctx()))

    # build_command runs first, then spawn, then one map_native_event per
    # non-empty line.
    assert adapter.calls == [
        "build_command",
        "spawn",
        "map_native_event",
        "map_native_event",
    ]
    assert [e.type for e in events] == ["assistant_text", "assistant_text"]
    assert [e.data["text"] for e in events] == ["hello", "world"]


def test_cli_map_native_event_returning_none_drops_the_event() -> None:
    class DroppingCLIAdapter(FakeCLIAdapter):
        def map_native_event(self, native: dict[str, Any]) -> BackendEvent | None:
            self.calls.append("map_native_event")
            return None

    adapter = DroppingCLIAdapter()
    assert list(adapter.run(_ctx())) == []


def test_cli_supports_live_gating_defaults_true() -> None:
    assert FakeCLIAdapter().supports_live_gating() is True


# --- APIAdapter -------------------------------------------------------------


class FakeAPIAdapter(APIAdapter):
    """An API adapter with scriptable request/map_response/execute hooks."""

    vendor = "anthropic"
    surface = "api"

    def __init__(
        self, *, map_responses: list[tuple[list[BackendEvent], list[dict[str, Any]]]]
    ) -> None:
        super().__init__()
        # Each call to map_response pops the next scripted (events, tool_calls).
        self._map_responses = list(map_responses)
        self.calls: list[str] = []
        self.requests: list[dict[str, Any]] = []
        self.executed: list[dict[str, Any]] = []
        self.messages_seen: list[list[dict[str, Any]]] = []

    def auth_headers(self, env: dict[str, str]) -> dict[str, str]:
        self.calls.append("auth_headers")
        return {"Authorization": f"Bearer {env.get('CRAIK_TOKEN', '')}"}

    def request(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]],
        env: dict[str, str],
    ) -> dict[str, Any]:
        self.calls.append("request")
        self.requests.append({"tools": tools, "headers": self.auth_headers(env)})
        self.messages_seen.append([dict(m) for m in messages])
        return {"step": len(self.requests)}

    def map_response(
        self, response: dict[str, Any]
    ) -> tuple[list[BackendEvent], list[dict[str, Any]]]:
        self.calls.append("map_response")
        return self._map_responses.pop(0)

    def execute_tool(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        self.calls.append("execute_tool")
        self.executed.append(tool_call)
        return {"tool_call_id": tool_call["id"], "result": "ok"}


def test_api_tool_loop_allows_executes_and_continues() -> None:
    tool_call = {"id": "t1", "name": "write_file"}
    adapter = FakeAPIAdapter(
        map_responses=[
            ([assistant_text_event(text="thinking", source="anthropic-api")], [tool_call]),
            ([assistant_text_event(text="done", source="anthropic-api")], []),
        ]
    )

    events = list(adapter.run(_ctx(decide=lambda req: "allow")))

    # Two model turns -> two requests; the allowed tool was executed once.
    assert adapter.calls.count("request") == 2
    assert adapter.executed == [tool_call]
    assert [e.data["text"] for e in events] == ["thinking", "done"]


def test_api_tool_loop_deny_does_not_execute() -> None:
    tool_call = {"id": "t1", "name": "rm_rf"}
    adapter = FakeAPIAdapter(
        map_responses=[
            ([], [tool_call]),
            ([assistant_text_event(text="ok", source="anthropic-api")], []),
        ]
    )

    list(adapter.run(_ctx(decide=lambda req: "deny")))

    assert adapter.executed == []
    # A denial result is still threaded back so the model can react.
    second_request_messages = adapter.messages_seen[1]
    assert any("deny" in str(m).lower() for m in second_request_messages)


# --- Governance: hosted-tool stripping --------------------------------------


class _ToolAPIAdapter(FakeAPIAdapter):
    """API adapter pre-seeded with one function tool + one hosted tool."""

    def __init__(self) -> None:
        super().__init__(map_responses=[])
        self.register_tool({"type": "function", "name": "write_file"})
        self.register_tool({"type": "web_search"})  # vendor hosted/server-side


def test_governed_tools_strips_hosted_when_opt_out_disabled() -> None:
    adapter = _ToolAPIAdapter()
    assert adapter.allow_hosted_tools is False

    tools = adapter.function_tools()

    assert all(t["type"] == "function" for t in tools)
    assert [t["name"] for t in tools] == ["write_file"]
    assert not any(t["type"] == "web_search" for t in tools)


def test_governed_tools_passes_hosted_through_with_audited_opt_out() -> None:
    adapter = _ToolAPIAdapter()
    adapter.allow_hosted_tools = True

    tools = adapter.function_tools()

    types = sorted(t["type"] for t in tools)
    assert types == ["function", "web_search"]


def test_governed_tools_is_pure_and_filters_supplied_specs() -> None:
    adapter = _ToolAPIAdapter()
    specs = [
        {"type": "function", "name": "a"},
        {"type": "code_interpreter"},
        {"type": "file_search"},
        {"type": "function", "name": "b"},
    ]

    filtered = adapter._governed_tools(specs)

    assert [t["name"] for t in filtered] == ["a", "b"]


def test_api_supports_live_gating_defaults_true() -> None:
    adapter = FakeAPIAdapter(map_responses=[])
    assert adapter.supports_live_gating() is True
