"""Regression + defense-in-depth guard: live CLI ``run()`` emits contract-valid
events, and EVERY ``receipt.created`` carries a non-empty ``run_id``.

Reproduces the production-blocking crash a real dogfooding session hit:

    Gateway backend emitted invalid event receipt.created:
    event 0 receipt.created: run_id is required

Root cause was that the three CLI adapters' ``map_native_event`` mapped the
Claude/Codex/Gemini end-of-run ``result`` / ``turn.completed`` native line to a
synthetic ``receipt.created`` built WITHOUT a ``run_id`` (and with a hardcoded
``receipt_id``). The gateway event contract requires a non-empty ``run_id`` on
``receipt.created``, so the Rust TUI's gateway validation rejected it and the
session died.

These tests drive the REAL ``run()`` path with a FAKE subprocess (the same
``local_process_backend`` Popen seam ``test_cli_run.py`` / ``test_typed_run.py``
fake), run EVERY emitted event through ``validate_event``, and assert that every
``receipt.created`` carries a real persisted ``receipt_id`` + non-empty
``run_id`` -- and that at least one canonical receipt is emitted (no
governance regression: a real run must never produce ZERO audit receipts).
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from craik.runtime.auth.profile import AuthProfile, CredentialKind
from craik.runtime.auth.store import AuthProfileStore
from craik.runtime.backend.adapters.anthropic_cli import AnthropicCLI
from craik.runtime.backend.adapters.base import RunContext
from craik.runtime.backend.adapters.google_cli import GoogleCLI
from craik.runtime.backend.adapters.openai_cli import OpenAICLI
from craik.runtime.backend.events import BackendEvent, validate_event
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.store import LocalStore

_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "adapters"
_GEMINI_FIXTURE = _FIXTURE_DIR / "gemini_cli_stream_raw.jsonl"
_CODEX_FIXTURE = _FIXTURE_DIR / "codex_exec_stream_raw.jsonl"


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik")}


def _repo(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    return repo


def _ctx(env: dict[str, str]) -> RunContext:
    return RunContext(
        prompt="Review the implementation plan",
        env=env,
        emit=lambda event: None,
        decide=lambda request: "allow",
        require_operator_approval=False,
    )


class _FakeProcess:
    """Minimal Popen stand-in yielding recorded lines then a clean exit."""

    def __init__(self, lines: list[str]) -> None:
        self.stdout = iter(line if line.endswith("\n") else line + "\n" for line in lines)
        self.returncode = 0

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 0


def _install_fake_subprocess(monkeypatch, binary: str, fixture: Path) -> None:
    original_popen = subprocess.Popen
    lines = fixture.read_text(encoding="utf-8").splitlines()

    def _popen(args, **kwargs):
        if Path(args[0]).name != binary:
            return original_popen(args, **kwargs)
        return _FakeProcess(lines)

    monkeypatch.setattr("craik.runtime.sandbox.local_process_backend.subprocess.Popen", _popen)


def _install_claude_marker_subprocess(monkeypatch) -> None:
    original_popen = subprocess.Popen

    monkeypatch.setattr(
        "craik.runtime.backend.claude_code.shutil.which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    class _Process:
        stdout = iter(
            [
                (
                    '{"type":"assistant","message":{"content":[{"type":"tool_use",'
                    '"name":"Read","input":{"file_path":"README.md"}}]}}\n'
                ),
                (
                    '{"type":"assistant","message":{"content":[{"type":"text",'
                    '"text":"Reviewing the plan now."}]}}\n'
                ),
                '{"type":"result","result":"done from typed run"}\n',
            ]
        )

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    def _popen(args, **kwargs):
        if Path(args[0]).name != "claude":
            return original_popen(args, **kwargs)
        return _Process()

    monkeypatch.setattr(
        "craik.runtime.sandbox.local_process_backend.subprocess.Popen",
        _popen,
    )


def _claude_cli_marker_profile() -> AuthProfile:
    return AuthProfile(
        id="anthropic:default",
        kind=CredentialKind.MARKER,
        provider_family="anthropic",
        metadata={"external_runtime": "claude-cli", "credential_mode": "claude-cli"},
        created_at=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
        last_status="ok",
    )


def _assert_every_event_contract_valid_with_receipt_run_id(
    events: list[BackendEvent], env: dict[str, str]
) -> None:
    """Every event passes the gateway contract; every receipt has a run_id.

    This is the exact validation the Rust TUI gateway applies; it rejected the
    run-id-less receipt and crashed the session. Also confirms NO governance
    regression: at least one ``receipt.created`` is emitted, and every emitted
    receipt id is readable from a fresh store (a real persisted receipt, not a
    synthetic stub).
    """
    # Contract validation over the WHOLE sequence -- the gateway rejects on the
    # first violation, exactly the crash this test reproduces.
    for event in events:
        validate_event(event)

    receipts = [e for e in events if e.type == "receipt.created"]
    assert receipts, "a real run must emit at least one receipt.created (no zero-receipt run)"
    for receipt in receipts:
        assert receipt.run_id, f"receipt.created must carry a non-empty run_id: {receipt!r}"

    reopened = LocalStore.from_env(env)
    try:
        reopened.initialize()
        for receipt in receipts:
            receipt_id = receipt.data["receipt_id"]
            assert reopened.get_receipt(receipt_id) is not None, (
                f"emitted receipt {receipt_id} must be a real persisted receipt"
            )
    finally:
        reopened.close()


def test_anthropic_cli_run_emits_only_contract_valid_receipts(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    AuthProfileStore.from_env(env).put(_claude_cli_marker_profile())
    dispatch_slash_command("/model set anthropic/claude-sonnet-4-20250514", env=env)
    _install_claude_marker_subprocess(monkeypatch)

    adapter = AnthropicCLI(original_env=env)
    events = list(adapter.run(_ctx(env)))

    _assert_every_event_contract_valid_with_receipt_run_id(events, env)


def test_google_cli_run_emits_only_contract_valid_receipts(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    _install_fake_subprocess(monkeypatch, "gemini", _GEMINI_FIXTURE)

    adapter = GoogleCLI(original_env=env)
    events = list(adapter.run(_ctx(env)))

    _assert_every_event_contract_valid_with_receipt_run_id(events, env)


def test_openai_cli_run_emits_only_contract_valid_receipts(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)
    _install_fake_subprocess(monkeypatch, "codex", _CODEX_FIXTURE)

    adapter = OpenAICLI(original_env=env)
    events = list(adapter.run(_ctx(env)))

    _assert_every_event_contract_valid_with_receipt_run_id(events, env)


@pytest.mark.parametrize(
    ("adapter_factory", "native_result_line"),
    [
        (AnthropicCLI, {"kind": "result", "result": "done"}),
        (GoogleCLI, {"type": "result"}),
        (
            OpenAICLI,
            {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
        ),
    ],
)
def test_result_line_does_not_map_to_run_id_less_receipt(
    adapter_factory, native_result_line
) -> None:
    """The end-of-run ``result`` / ``turn.completed`` native line must NOT map to
    a ``receipt.created`` -- the canonical receipt (with run_id) is owned by the
    framing / ``run_cli_typed`` path. A mapped receipt here would lack a run_id
    and crash the gateway.
    """
    adapter = adapter_factory()
    event = adapter.map_native_event(native_result_line)

    assert event is None or event.type != "receipt.created", (
        "the result/turn line must not synthesize a (run-id-less) receipt.created"
    )
