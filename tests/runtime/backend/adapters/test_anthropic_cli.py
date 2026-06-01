"""Tests for the real ``AnthropicCLI`` adapter (Phase 4 exemplar).

Feeds recorded Claude Code ``--output-format stream-json`` lines through the
adapter's TEMPLATE ``parse_stream`` surface and asserts the canonical typed-event
sequence: a single coalesced ``assistant_text``, a ``tool.used``, an
``approval.*`` event -- and NO per-line ``receipt.created`` (the end-of-run
``result`` line is dropped here; the canonical receipt, carrying ``run_id``, is
owned by the live ``run()`` framing -- see ``test_typed_run.py`` /
``test_cli_receipt_run_id_guard.py``) -- with NO ``craik.runner_step_result`` /
``craik.handoff`` envelope leakage.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from craik.runtime.backend.adapters.anthropic_cli import AnthropicCLI
from craik.runtime.backend.adapters.base import RunContext
from craik.runtime.backend.adapters.registry import select_adapter
from craik.runtime.backend.events import BackendEvent

_RAW_FIXTURE = Path("tests/fixtures/adapters/claude_code_stream_raw.jsonl")


def _fixture_lines() -> list[str]:
    return _RAW_FIXTURE.read_text(encoding="utf-8").splitlines()


def _run_fixture() -> list[BackendEvent]:
    """Drive the fixture through the CLI TEMPLATE surface (build_command -> spawn ->
    parse_stream).

    Task 5.5a repurposes ``AnthropicCLI.run`` as the live path that composes the
    audited claude core (the core spawns), so ``run`` no longer reads the injected
    ``spawn``. The template hooks (``build_command`` / ``spawn`` / ``parse_stream``)
    remain the abstract CLI surface that maps a native stream to typed events; this
    fixture test exercises THAT surface directly via ``parse_stream`` over a fake
    ``spawn``, which is exactly the path the typed ``run`` re-uses through
    ``map_native_event`` + the Coalescer.
    """
    adapter = AnthropicCLI()
    lines = _fixture_lines()

    def fake_spawn(cmd: list[str], env: dict[str, str]) -> Iterable[str]:
        return lines

    adapter.spawn = fake_spawn  # type: ignore[method-assign]
    ctx = RunContext(
        prompt="Review the implementation plan for the next phase",
        env={},
        emit=lambda event: None,
        decide=lambda request: "allow",
        require_operator_approval=False,
    )
    cmd = adapter.build_command(ctx)
    return list(adapter.parse_stream(adapter.spawn(cmd, ctx.env), ctx))


def test_supports_live_gating_is_true() -> None:
    assert AnthropicCLI().supports_live_gating() is True


def test_select_adapter_returns_real_anthropic_cli() -> None:
    adapter = select_adapter("anthropic-cli", {})

    assert isinstance(adapter, AnthropicCLI)
    assert adapter.vendor == "anthropic"
    assert adapter.surface == "cli"


def test_build_command_uses_claude_stream_json_argv() -> None:
    adapter = AnthropicCLI()
    ctx = RunContext(
        prompt="hi",
        env={},
        emit=lambda event: None,
        decide=lambda request: "allow",
        require_operator_approval=False,
    )

    cmd = adapter.build_command(ctx)

    # The executable resolves via ``shutil.which`` when present, so assert on
    # the basename rather than the (environment-dependent) absolute path.
    assert Path(cmd[0]).name == "claude"
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--verbose" in cmd


def test_default_vendor_profile_is_anthropic() -> None:
    assert AnthropicCLI().vendor_profile.vendor == "anthropic"


def test_auth_source_names_claude_cli_marker() -> None:
    # Auth is delegated to the existing claude-cli marker profile, not a new
    # OAuth flow. The adapter only needs to NAME its auth source.
    assert "claude" in AnthropicCLI().auth_source().lower()


def test_event_sequence_is_canonical() -> None:
    events = _run_fixture()
    types = [event.type for event in events]

    # Exactly one coalesced assistant_text (superseded, not concatenated).
    assert types.count("assistant_text") == 1
    assert "tool.used" in types
    assert any(t.startswith("approval.") for t in types)
    # The ``parse_stream`` surface NO LONGER synthesizes a per-line
    # ``receipt.created`` from the end-of-run ``result`` line: that record was
    # run-id-less + hardcoded-id and the gateway event contract rejected it. The
    # CANONICAL receipt (with run_id) is emitted by the live ``run()`` framing
    # (``claude_framing_events``), exercised in ``test_typed_run.py`` +
    # ``test_cli_receipt_run_id_guard.py``.
    assert "receipt.created" not in types


def test_assistant_text_is_coalesced_not_concatenated() -> None:
    events = _run_fixture()
    text_events = [e for e in events if e.type == "assistant_text"]

    assert len(text_events) == 1
    text = text_events[0].data["text"]
    # The latest cumulative snapshot supersedes earlier prefixes; the early
    # "Reviewing the" prefix must NOT appear twice (no append/concat).
    assert text.count("Reviewing the plan") == 1


def test_result_line_maps_to_no_receipt() -> None:
    # The end-of-run ``result`` line must NOT synthesize a ``receipt.created``:
    # the canonical receipt (with run_id) is owned by the live ``run()`` framing.
    # A receipt mapped here would lack a run_id and crash the gateway. The
    # delegated-observed posture of the CANONICAL receipt is asserted in
    # ``test_typed_run.py`` / ``test_cli_receipt_run_id_guard.py``.
    adapter = AnthropicCLI()

    assert adapter.map_native_event({"kind": "result", "result": "done"}) is None


def test_every_event_sources_anthropic_cli() -> None:
    events = _run_fixture()

    assert events
    assert all(event.source == "anthropic-cli" for event in events)


def test_no_contract_envelope_sections_leak() -> None:
    events = _run_fixture()
    blob = "\n".join(str(event.as_dict()) for event in events)

    assert "craik.runner_step_result" not in blob
    assert "craik.handoff" not in blob
