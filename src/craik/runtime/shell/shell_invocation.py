"""Audited local shell invocation support for the terminal UI."""

from __future__ import annotations

import getpass
import hashlib
import os
import shlex
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from craik.contracts.models import SandboxBackend, SandboxBackendCapability, ShellInvocationReceipt
from craik.runtime.auth.operator import (
    OperatorSessionNotFoundError,
    OperatorSessionStore,
)
from craik.runtime.paths import ensure_craik_home
from craik.runtime.policy.redaction import redact
from craik.runtime.sandbox.local_process_backend import (
    LocalProcessCommand,
    LocalProcessCommandRegistry,
    LocalProcessRequest,
    execute_local_process_command,
)
from craik.runtime.store import LocalStore
from craik.runtime.store.integrity import contract_hmac, hmac_key_for_store

SHELL_PREVIEW_LIMIT = 4096


@dataclass(frozen=True)
class ShellInvocationResult:
    """Operator-facing shell invocation result."""

    command: str
    exit_code: int
    stdout_preview: str
    stderr_preview: str
    receipt_id: str
    stdout_log: Path
    stderr_log: Path

    @property
    def transcript_text(self) -> str:
        """Return a compact transcript block for the TUI."""
        output = self.stdout_preview or self.stderr_preview or "(no output)"
        return (
            f"shell {self.exit_code}: {self.command}\n"
            f"{output}\n"
            f"receipt: {self.receipt_id}"
        )


def is_shell_invocation_text(text: str) -> bool:
    """Return whether TUI input requests local shell invocation mode."""
    return text.lstrip().startswith("!")


def shell_command_from_text(text: str) -> str:
    """Extract the shell command from a ``!``-prefixed TUI input."""
    stripped = text.lstrip()
    return stripped[1:].strip()


def run_shell_invocation(
    text: str,
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> ShellInvocationResult:
    """Run one ``!``-prefixed shell invocation and persist its receipt."""
    command = shell_command_from_text(text)
    if not command:
        raise ValueError("shell invocation requires a command after !")
    argv = shlex.split(command)
    if not argv:
        raise ValueError("shell invocation requires a command after !")

    values = dict(os.environ) if env is None else dict(env)
    working_directory = cwd or Path.cwd()
    receipt_id = f"shell_invocation_{uuid.uuid4().hex}"
    command_ref = f"shell:{hashlib.sha256(command.encode('utf-8')).hexdigest()[:16]}"
    backend = _local_process_backend()
    registry = LocalProcessCommandRegistry(
        [
            LocalProcessCommand(
                ref=command_ref,
                argv=argv,
                cwd=working_directory,
                timeout_seconds=30,
            )
        ]
    )
    request = LocalProcessRequest(
        id=f"local_process_{uuid.uuid4().hex}",
        backend_id=backend.id,
        command_ref=command_ref,
        policy_envelope_id="tui_shell_invocation_policy",
        capability_grant_id="tui_shell_invocation_grant",
        receipt_id=receipt_id,
        working_directory_ref=str(working_directory),
    )
    started = time.monotonic()
    execution = execute_local_process_command(
        backend=backend,
        request=request,
        registry=registry,
    )
    duration_ms = round((time.monotonic() - started) * 1000)
    stdout_redaction = redact(execution.stdout)
    stderr_redaction = redact(execution.stderr)
    stdout = str(stdout_redaction.value)
    stderr = str(stderr_redaction.value)
    stdout_hash = _sha256_text(stdout)
    stderr_hash = _sha256_text(stderr)
    paths = ensure_craik_home(values)
    stdout_log = _write_side_log(paths.state, stdout_hash, "stdout", stdout)
    stderr_log = _write_side_log(paths.state, stderr_hash, "stderr", stderr)
    command_redaction = redact(command)
    receipt = ShellInvocationReceipt(
        receipt_id=receipt_id,
        timestamp=datetime.now(UTC),
        operator_subject=_operator_subject(values),
        command=str(command_redaction.value),
        exit_code=execution.returncode if execution.returncode is not None else 1,
        stdout_preview=_preview(stdout),
        stderr_preview=_preview(stderr),
        stdout_sha256=stdout_hash,
        stderr_sha256=stderr_hash,
        working_directory=str(working_directory),
        duration_ms=duration_ms,
        redactions_applied=sorted(
            {
                *command_redaction.redacted_paths,
                *stdout_redaction.redacted_paths,
                *stderr_redaction.redacted_paths,
            }
        ),
    )
    _persist_receipt(values, receipt)
    return ShellInvocationResult(
        command=receipt.command,
        exit_code=receipt.exit_code,
        stdout_preview=receipt.stdout_preview,
        stderr_preview=receipt.stderr_preview,
        receipt_id=receipt.receipt_id,
        stdout_log=stdout_log,
        stderr_log=stderr_log,
    )


def shell_output_path(state_dir: Path, digest: str, stream: str) -> Path:
    """Return the side-log path for a shell invocation output stream."""
    return state_dir / "shell-output" / f"{digest}.{stream}.log"


def _persist_receipt(env: dict[str, str], receipt: ShellInvocationReceipt) -> None:
    paths = ensure_craik_home(env)
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        payload = receipt.model_dump(mode="json", by_alias=True)
        signed = receipt.model_copy(
            update={"receipt_hmac": contract_hmac(payload, hmac_key_for_store(store))}
        )
        store.put_contract(signed)
    finally:
        store.close()


def _write_side_log(state_dir: Path, digest: str, stream: str, text: str) -> Path:
    path = shell_output_path(state_dir, digest, stream)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o600)
    return path


def _preview(text: str) -> str:
    return text[:SHELL_PREVIEW_LIMIT]


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _operator_subject(env: dict[str, str]) -> str:
    try:
        session = OperatorSessionStore.from_env(env).get()
    except OperatorSessionNotFoundError:
        return f"local-user:{getpass.getuser()}"
    return session.subject


def _local_process_backend() -> SandboxBackend:
    return SandboxBackend(
        id="sandbox_backend_tui_shell",
        name="TUI Shell Local Process",
        kind="local_process",
        isolation_mode="process",
        capabilities=[
            SandboxBackendCapability(
                name="shell.execute",
                operations=["run"],
                description="Execute operator-triggered TUI shell commands.",
            )
        ],
        docs=["docs/guides/terminal-ui.md"],
        created_at=datetime.now(UTC),
    )
