"""Tests for the observe-only ``OpenAICLI`` adapter (Phase 4).

Unlike the gating CLI exemplars (``AnthropicCLI`` / ``GoogleCLI``), this surface
CANNOT live-gate: Codex's pre-tool hook does not fire for the shell tool under
``codex exec`` (verified negative, see ``docs/adapters/vendor-capabilities.md``).
So ``supports_live_gating`` is ``False``, asking it to gate raises
``LiveGatingUnsupported`` (pointing operators to the ``openai-api`` surface), and
the receipts it emits attest OBSERVATION only -- ``decided_by="bypass"`` (the
ungoverned audit flag), NOT the ``operator`` value the gating CLIs stamp.

Feeds recorded ``codex exec --json`` lines (the ``thread`` / ``turn`` / ``item.*``
vocabulary) through the adapter's TEMPLATE ``parse_stream`` surface and asserts
the canonical observe sequence: a single coalesced ``assistant_text``, a
``tool.used``, and NO per-line ``receipt.created`` (the end-of-turn
``turn.completed`` line is dropped here; the canonical observe-only receipt,
carrying ``run_id``, is owned by the live ``run()`` framing -- see
``test_cli_run.py`` / ``test_cli_receipt_run_id_guard.py``) -- with NO
contract-envelope leakage.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

from craik.runtime.backend.adapters.base import RunContext
from craik.runtime.backend.adapters.openai_cli import LiveGatingUnsupported, OpenAICLI
from craik.runtime.backend.adapters.registry import select_adapter
from craik.runtime.backend.events import BackendEvent

_RAW_FIXTURE = Path("tests/fixtures/adapters/codex_exec_stream_raw.jsonl")


def _fixture_lines() -> list[str]:
    return _RAW_FIXTURE.read_text(encoding="utf-8").splitlines()


def _ctx(
    *, require_operator_approval: bool = False, env: dict[str, str] | None = None
) -> RunContext:
    return RunContext(
        prompt="Review the implementation plan for the next phase",
        env=env if env is not None else {},
        emit=lambda event: None,
        decide=lambda request: "allow",
        require_operator_approval=require_operator_approval,
    )


def _run_fixture() -> list[BackendEvent]:
    # Task 5.5b repurposes ``OpenAICLI.run`` as the live path composing the
    # audited CLI core (the core spawns the real subprocess), so ``run`` no
    # longer reads the injected ``spawn``. The template hooks remain the abstract
    # CLI surface; this exercises THAT surface via ``parse_stream`` over a fake
    # ``spawn`` -- exactly the path the typed ``run`` re-uses through
    # ``map_native_event`` + the ``Coalescer``.
    adapter = OpenAICLI()
    lines = _fixture_lines()

    def fake_spawn(cmd: list[str], env: dict[str, str]) -> Iterable[str]:
        return lines

    adapter.spawn = fake_spawn  # type: ignore[method-assign]
    ctx = _ctx()
    return list(adapter.parse_stream(adapter.spawn(adapter.build_command(ctx), ctx.env), ctx))


def test_supports_live_gating_is_false() -> None:
    assert OpenAICLI().supports_live_gating() is False


def test_select_adapter_returns_real_openai_cli() -> None:
    adapter = select_adapter("openai-cli", {})

    assert isinstance(adapter, OpenAICLI)
    assert adapter.vendor == "openai"
    assert adapter.surface == "cli"


def test_require_live_gating_raises_pointing_to_api_surface() -> None:
    with pytest.raises(LiveGatingUnsupported) as excinfo:
        OpenAICLI().require_live_gating()

    # The message must steer operators to the live-governance surface.
    assert "openai-api" in str(excinfo.value)


def test_run_refuses_when_operator_approval_required() -> None:
    adapter = OpenAICLI()

    with pytest.raises(LiveGatingUnsupported) as excinfo:
        list(adapter.run(_ctx(require_operator_approval=True)))

    assert "openai-api" in str(excinfo.value)


def test_build_command_uses_codex_exec_json_argv() -> None:
    cmd = OpenAICLI().build_command(_ctx())

    assert Path(cmd[0]).name == "codex"
    assert "exec" in cmd
    assert "--json" in cmd
    # No sandbox env var set -> the flag is absent (capture, don't force).
    assert "--sandbox" not in cmd


def test_build_command_appends_sandbox_when_set() -> None:
    cmd = OpenAICLI().build_command(_ctx(env={"CRAIK_CODEX_SANDBOX_MODE": "workspace-write"}))

    assert "--sandbox" in cmd
    assert cmd[cmd.index("--sandbox") + 1] == "workspace-write"


def test_build_command_omits_invalid_sandbox_mode() -> None:
    # A Claude-only value is not a real Codex sandbox mode -> dropped.
    cmd = OpenAICLI().build_command(_ctx(env={"CRAIK_CODEX_SANDBOX_MODE": "bypassPermissions"}))

    assert "--sandbox" not in cmd


def test_default_vendor_profile_is_openai() -> None:
    assert OpenAICLI().profile.vendor == "openai"


def test_auth_source_names_openai_api_key_source() -> None:
    # Auth is delegated to the existing OpenAI api-key credential source (NAME
    # only); the CLI surface has no sanctioned headless subscription token.
    assert "openai" in OpenAICLI().auth_source().lower()


def test_event_sequence_is_canonical_observe() -> None:
    events = _run_fixture()
    types = [event.type for event in events]

    assert types.count("assistant_text") == 1
    assert "tool.used" in types
    # NO per-line receipt: the end-of-turn ``turn.completed`` line is dropped
    # here. That synthetic per-line receipt was run-id-less + hardcoded-id and the
    # gateway event contract rejected it. The CANONICAL observe-only receipt (with
    # run_id) is emitted by the live ``run()`` framing (``cli_framing_events``),
    # exercised in ``test_cli_run.py`` + ``test_cli_receipt_run_id_guard.py``.
    receipts = [e for e in events if e.type == "receipt.created"]
    assert receipts == []


def test_assistant_text_is_coalesced_not_concatenated() -> None:
    events = _run_fixture()
    text_events = [e for e in events if e.type == "assistant_text"]

    assert len(text_events) == 1
    text = text_events[0].data["text"]
    # The latest cumulative snapshot supersedes earlier prefixes (no concat).
    assert text.count("Reviewing the plan") == 1


def test_turn_completed_line_maps_to_no_receipt() -> None:
    # The end-of-turn ``turn.completed`` line must NOT synthesize a
    # ``receipt.created``: the canonical observe-only receipt (with run_id) is
    # owned by the live ``run()`` framing (``cli_framing_events``), not the
    # per-line mapper. A receipt mapped here would lack a run_id and crash the
    # gateway. The observe-only attribution (``decided_by="bypass"``, never
    # ``operator``) of the CANONICAL receipt is asserted in ``test_cli_run.py``.
    adapter = OpenAICLI()

    assert adapter.map_native_event({"type": "turn.completed"}) is None


def test_every_event_sources_openai_cli() -> None:
    events = _run_fixture()

    assert events
    assert all(event.source == "openai-cli" for event in events)


def test_no_contract_envelope_sections_leak() -> None:
    events = _run_fixture()
    blob = "\n".join(str(event.as_dict()) for event in events)

    assert "craik.runner_step_result" not in blob
    assert "craik.handoff" not in blob
