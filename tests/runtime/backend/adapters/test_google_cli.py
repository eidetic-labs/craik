"""Tests for the real ``GoogleCLI`` adapter (Phase 4, mirrors the exemplar).

Feeds recorded Gemini CLI ``--output-format stream-json`` lines through the
adapter's TEMPLATE ``parse_stream`` surface and asserts the canonical typed-event
sequence: a single coalesced ``assistant_text``, a ``tool.used``, and NO per-line
``receipt.created`` (the end-of-run ``result`` line is dropped here; the canonical
receipt, carrying ``run_id``, is owned by the live ``run()`` framing -- see
``test_cli_run.py`` / ``test_cli_receipt_run_id_guard.py``) -- with NO
``craik.runner_step_result`` / ``craik.handoff`` envelope leakage. Every event
sources ``google-cli``.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from craik.runtime.backend.adapters.base import RunContext
from craik.runtime.backend.adapters.google_cli import GoogleCLI
from craik.runtime.backend.adapters.registry import select_adapter
from craik.runtime.backend.events import BackendEvent

_RAW_FIXTURE = Path("tests/fixtures/adapters/gemini_cli_stream_raw.jsonl")


def _fixture_lines() -> list[str]:
    return _RAW_FIXTURE.read_text(encoding="utf-8").splitlines()


def _run_fixture() -> list[BackendEvent]:
    # Task 5.5b repurposes ``GoogleCLI.run`` as the live path composing the
    # audited CLI core (the core spawns the real subprocess), so ``run`` no
    # longer reads the injected ``spawn``. The template hooks remain the abstract
    # CLI surface; this exercises THAT surface via ``parse_stream`` over a fake
    # ``spawn`` -- exactly the path the typed ``run`` re-uses through
    # ``map_native_event`` + the ``Coalescer``.
    adapter = GoogleCLI()
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
    return list(adapter.parse_stream(adapter.spawn(adapter.build_command(ctx), ctx.env), ctx))


def test_supports_live_gating_is_true() -> None:
    assert GoogleCLI().supports_live_gating() is True


def test_select_adapter_returns_real_google_cli() -> None:
    adapter = select_adapter("google-cli", {})

    assert isinstance(adapter, GoogleCLI)
    assert adapter.vendor == "google"
    assert adapter.surface == "cli"


def test_build_command_uses_gemini_stream_json_argv() -> None:
    adapter = GoogleCLI()
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
    assert Path(cmd[0]).name == "gemini"
    assert "-p" in cmd
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    # No approval-mode env var set -> the flag is absent (capture, don't force).
    assert "--approval-mode" not in cmd


def test_build_command_appends_approval_mode_when_set() -> None:
    adapter = GoogleCLI()
    ctx = RunContext(
        prompt="hi",
        env={"CRAIK_GEMINI_APPROVAL_MODE": "yolo"},
        emit=lambda event: None,
        decide=lambda request: "allow",
        require_operator_approval=False,
    )

    cmd = adapter.build_command(ctx)

    assert "--approval-mode" in cmd
    assert cmd[cmd.index("--approval-mode") + 1] == "yolo"


def test_build_command_omits_invalid_approval_mode() -> None:
    adapter = GoogleCLI()
    ctx = RunContext(
        prompt="hi",
        # A Claude-only value is not a real Gemini approval mode -> dropped.
        env={"CRAIK_GEMINI_APPROVAL_MODE": "bypassPermissions"},
        emit=lambda event: None,
        decide=lambda request: "allow",
        require_operator_approval=False,
    )

    cmd = adapter.build_command(ctx)

    assert "--approval-mode" not in cmd


def test_default_vendor_profile_is_google() -> None:
    assert GoogleCLI().profile.vendor == "google"


def test_auth_source_names_google_source() -> None:
    # Auth is delegated to the existing google credential source (API key /
    # Vertex SA), not a new OAuth flow. The adapter only needs to NAME it.
    assert "google" in GoogleCLI().auth_source().lower()


def test_workspace_trust_env_is_set() -> None:
    adapter = GoogleCLI()
    env: dict[str, str] = {}

    spawn_env = adapter.spawn_env(env)

    assert spawn_env["GEMINI_CLI_TRUST_WORKSPACE"] == "true"


def test_event_sequence_is_canonical() -> None:
    events = _run_fixture()
    types = [event.type for event in events]

    # Exactly one coalesced assistant_text (superseded, not concatenated).
    assert types.count("assistant_text") == 1
    assert "tool.used" in types
    # NO per-line receipt: the end-of-run ``result`` line is dropped here (as is
    # the intermediate ``tool_result``). That synthetic per-line receipt was
    # run-id-less + hardcoded-id and the gateway event contract rejected it. The
    # CANONICAL receipt (with run_id) is emitted by the live ``run()`` framing
    # (``cli_framing_events``), exercised in ``test_cli_run.py`` +
    # ``test_cli_receipt_run_id_guard.py``.
    receipts = [e for e in events if e.as_dict()["type"] == "receipt.created"]
    assert receipts == []


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
    # the canonical receipt (with run_id) is owned by the live ``run()`` framing
    # (``cli_framing_events``), not the per-line mapper. A receipt mapped here
    # would lack a run_id and crash the gateway. The delegated-observed posture of
    # the CANONICAL receipt is asserted in ``test_cli_run.py`` /
    # ``test_cli_receipt_run_id_guard.py``.
    adapter = GoogleCLI()

    assert adapter.map_native_event({"type": "result"}) is None


def test_every_event_sources_google_cli() -> None:
    events = _run_fixture()

    assert events
    assert all(event.source == "google-cli" for event in events)


def test_no_contract_envelope_sections_leak() -> None:
    events = _run_fixture()
    blob = "\n".join(str(event.as_dict()) for event in events)

    assert "craik.runner_step_result" not in blob
    assert "craik.handoff" not in blob
