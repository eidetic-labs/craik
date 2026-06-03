"""Approval Task 2: the audited Claude run always STARTS (no pre-run denial).

The Claude path is delegate-and-observe: Craik passes ``--permission-mode`` to
the ``claude`` CLI (Claude governs its own tools) and Craik OBSERVES the stream
and writes receipts. There is no live Craik operator gate on this path, so the
run must never be pre-denied -- and when no real operator approval occurred
(no ``CRAIK_CLAUDE_CODE_RUN_APPROVED=1`` flag), the receipts must HONESTLY read
as delegate-observed, not operator-approved.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from craik.runtime.backend import claude_code
from craik.runtime.backend.claude_code import execute_claude_code_run
from craik.runtime.store import LocalStore


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik")}


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    yield repo


def _stub_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the real ``claude`` spawn boundary so no subprocess runs."""

    def _fake(prompt: str, *, env: dict[str, str] | None) -> claude_code.ClaudeCodeExecution:
        return claude_code.ClaudeCodeExecution(
            text="stubbed claude output",
            raw_events=['{"type":"result","result":"stubbed claude output"}'],
            progress_events=[],
            structured_events=[{"type": "result", "result": "stubbed claude output"}],
        )

    monkeypatch.setattr(claude_code, "_execute_claude_code_prompt", _fake)


def test_run_starts_without_preapproval_flag(
    tmp_path: Path,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No ``CRAIK_CLAUDE_CODE_RUN_APPROVED`` flag must NOT pre-deny the run."""
    _stub_prompt(monkeypatch)
    env = _env(tmp_path)

    # require_operator_approval=True is the explicit-claude-code request shape
    # (run_helpers sets it for `--backend claude-code`). It must NOT raise.
    result = execute_claude_code_run("Upgrade Craik Docs", env, require_operator_approval=True)

    assert result["status"] == "completed"
    assert "stubbed claude output" in str(result["run_outputs"])


def test_no_approval_run_records_delegate_observed_receipt(
    tmp_path: Path,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a real operator approval, receipts read delegate-observed, not approved."""
    _stub_prompt(monkeypatch)
    env = _env(tmp_path)

    execute_claude_code_run("Upgrade Craik Docs", env, require_operator_approval=True)

    store = LocalStore.from_env(env)
    try:
        approval = store.get_receipt("receipt_upgrade_craik_docs_claude_code_approval")
        run_receipt = store.get_receipt("receipt_run_upgrade_craik_docs_claude_code")
    finally:
        store.close()

    assert approval is not None
    # Honest attribution: Craik delegated + observed; no operator decided.
    assert approval.actor == "system:craik"
    assert approval.capability == "authority.delegate"
    assert approval.result.metadata["approved"] is False
    assert approval.result.metadata["default_attested_backend"] is True

    assert run_receipt is not None
    assert run_receipt.result.metadata["operator_approved_grants"] is False
    assert run_receipt.result.metadata["default_attested_backend"] is True


def test_real_operator_approval_flag_records_operator_approved(
    tmp_path: Path,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the operator actually approved (TUI sets the flag), say so honestly."""
    _stub_prompt(monkeypatch)
    env = {**_env(tmp_path), "CRAIK_CLAUDE_CODE_RUN_APPROVED": "1"}

    execute_claude_code_run("Upgrade Craik Docs", env, require_operator_approval=True)

    store = LocalStore.from_env(env)
    try:
        approval = store.get_receipt("receipt_upgrade_craik_docs_claude_code_approval")
        run_receipt = store.get_receipt("receipt_run_upgrade_craik_docs_claude_code")
    finally:
        store.close()

    assert approval is not None
    assert approval.actor == "user:tui"
    assert approval.capability == "approval.decide"
    assert approval.result.metadata["approved"] is True
    assert approval.result.metadata["default_attested_backend"] is False

    assert run_receipt is not None
    assert run_receipt.result.metadata["operator_approved_grants"] is True
    assert run_receipt.result.metadata["default_attested_backend"] is False
