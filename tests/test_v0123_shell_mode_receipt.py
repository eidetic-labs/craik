from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import cast

from craik.contracts.models import ShellInvocationReceipt
from craik.runtime.paths import ensure_craik_home
from craik.runtime.shell.shell_invocation import (
    is_shell_invocation_text,
    run_shell_invocation,
    shell_output_path,
)
from craik.runtime.store import LocalStore
from craik.runtime.store.receipt_integrity import contract_receipt_hmac_status


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / "home")}


def _receipt(env: dict[str, str], receipt_id: str) -> ShellInvocationReceipt:
    paths = ensure_craik_home(env)
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        raw = store.get_contract("craik.shell_invocation_receipt", receipt_id)
        assert raw is not None
        return cast(ShellInvocationReceipt, raw)
    finally:
        store.close()


def test_shell_mode_detects_bang_prefix() -> None:
    assert is_shell_invocation_text("! echo hello") is True
    assert is_shell_invocation_text("  ! echo hello") is True
    assert is_shell_invocation_text("echo hello") is False


def test_shell_invocation_emits_hmac_receipt_and_side_logs(tmp_path: Path) -> None:
    env = _env(tmp_path)

    result = run_shell_invocation("! echo hello", env=env, cwd=tmp_path)
    receipt = _receipt(env, result.receipt_id)

    assert result.exit_code == 0
    assert result.stdout_preview == "hello\n"
    assert receipt.exit_code == 0
    assert receipt.command == "echo hello"
    assert receipt.stdout_preview == "hello\n"
    assert receipt.operator_subject.startswith("local-user:")
    assert result.stdout_log == shell_output_path(
        ensure_craik_home(env).state,
        receipt.stdout_sha256,
        "stdout",
    )
    assert result.stdout_log.read_text(encoding="utf-8") == "hello\n"
    assert result.stderr_log.read_text(encoding="utf-8") == ""
    if os.name == "posix":
        assert stat.S_IMODE(result.stdout_log.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(result.stdout_log.stat().st_mode) == 0o600

    store = LocalStore.from_paths(ensure_craik_home(env))
    try:
        store.initialize()
        assert contract_receipt_hmac_status(store, receipt) == "verified"
    finally:
        store.close()


def test_shell_invocation_redacts_command_and_preview(tmp_path: Path) -> None:
    env = _env(tmp_path)
    token = "sk-" + "test123456789"
    command = (
        f"! {sys.executable} -c \"print('Authorization: Bearer {token}')\" "
        f"--token={token}"
    )

    result = run_shell_invocation(command, env=env, cwd=tmp_path)
    receipt = _receipt(env, result.receipt_id)

    assert "[REDACTED]" in receipt.command
    assert "[REDACTED]" in receipt.stdout_preview
    assert token not in receipt.command
    assert token not in receipt.stdout_preview
    assert receipt.redactions_applied


def test_shell_invocation_stdout_sha_matches_side_log(tmp_path: Path) -> None:
    env = _env(tmp_path)

    result = run_shell_invocation("! echo digest", env=env, cwd=tmp_path)
    receipt = _receipt(env, result.receipt_id)

    assert result.stdout_log.name == f"{receipt.stdout_sha256}.stdout.log"
    assert result.stdout_log.read_text(encoding="utf-8") == "digest\n"
