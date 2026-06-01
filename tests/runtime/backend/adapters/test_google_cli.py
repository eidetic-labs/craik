"""Tests for the real ``GoogleCLI`` adapter (Phase 4, mirrors the exemplar).

Feeds recorded Gemini CLI ``--output-format stream-json`` lines through the
adapter and asserts the canonical typed-event sequence: a single coalesced
``assistant_text``, a ``tool.used``, and a ``receipt.created`` carrying the
delegated-observed governance posture -- with NO
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
    # EXACTLY ONE receipt: the end-of-run ``result`` line maps to the single
    # delegated-observed receipt; the intermediate ``tool_result`` line is
    # dropped (mirroring the AnthropicCLI exemplar). The fixture carries both a
    # ``tool_result`` and a ``result`` line, so this guards against the prior
    # double-emission bug.
    receipts = [e for e in events if e.as_dict()["type"] == "receipt.created"]
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.source == "google-cli"
    assert receipt.data["execution"] == "delegated-observed"


def test_assistant_text_is_coalesced_not_concatenated() -> None:
    events = _run_fixture()
    text_events = [e for e in events if e.type == "assistant_text"]

    assert len(text_events) == 1
    text = text_events[0].data["text"]
    # The latest cumulative snapshot supersedes earlier prefixes; the early
    # "Reviewing the" prefix must NOT appear twice (no append/concat).
    assert text.count("Reviewing the plan") == 1


def test_receipt_carries_delegated_observed_posture() -> None:
    events = _run_fixture()
    receipts = [e for e in events if e.type == "receipt.created"]

    # Exactly one receipt -- the ``result``-derived one; ``tool_result`` is
    # dropped for parity with the AnthropicCLI exemplar.
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.source == "google-cli"
    assert receipt.data["execution"] == "delegated-observed"
    assert receipt.data["purpose"] == "execution"
    assert receipt.data["decision"] in {"allow", "deny"}
    assert receipt.data["decided_by"] in {"operator", "policy", "bypass"}


def test_every_event_sources_google_cli() -> None:
    events = _run_fixture()

    assert events
    assert all(event.source == "google-cli" for event in events)


def test_no_contract_envelope_sections_leak() -> None:
    events = _run_fixture()
    blob = "\n".join(str(event.as_dict()) for event in events)

    assert "craik.runner_step_result" not in blob
    assert "craik.handoff" not in blob
