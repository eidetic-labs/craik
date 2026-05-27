"""Local process sandbox backend boundaries."""

from __future__ import annotations

# Local-process execution is restricted to registered argv lists and never uses shell=True.
import subprocess  # nosec B404
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from threading import Event
from typing import IO, Any, Literal

from pydantic import Field

from craik.contracts.models import CraikModel, SandboxBackend

LocalProcessDecisionStatus = Literal["allowed", "denied"]
LocalProcessTimeoutExpired = subprocess.TimeoutExpired


class LocalProcessRequest(CraikModel):
    """Policy-bound request to run a local process command reference."""

    id: str
    backend_id: str
    command_ref: str
    operation: Literal["run"] = "run"
    capability: Literal["shell.execute"] = "shell.execute"
    policy_envelope_id: str | None = None
    capability_grant_id: str | None = None
    receipt_id: str | None = None
    working_directory_ref: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class LocalProcessDecision(CraikModel):
    """Decision for a local process backend request."""

    status: LocalProcessDecisionStatus
    allowed: bool
    reason: str
    backend_id: str
    command_ref: str
    required_controls: list[str] = Field(default_factory=list)


class LocalProcessCommand(CraikModel):
    """Registered command reference that can execute without shell expansion."""

    ref: str
    argv: list[str] = Field(min_length=1)
    cwd: Path | None = None
    timeout_seconds: float = 30.0
    metadata: dict[str, str] = Field(default_factory=dict)


class LocalProcessExecution(CraikModel):
    """Observed local process execution result."""

    allowed: bool
    executed: bool
    reason: str
    backend_id: str
    command_ref: str
    argv: list[str] = Field(default_factory=list)
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    timeout_seconds: float | None = None
    cancelled: bool = False


class LocalProcessStartError(RuntimeError):
    """Raised when a reviewed local process command cannot be started."""


class LocalProcessCommandRegistry:
    """In-memory registry of command references allowed for local execution."""

    def __init__(self, commands: list[LocalProcessCommand] | None = None) -> None:
        self._commands = {command.ref: command for command in commands or []}

    @classmethod
    def from_mapping(cls, mapping: dict[str, object]) -> LocalProcessCommandRegistry:
        commands: list[LocalProcessCommand] = []
        for ref, raw in mapping.items():
            if isinstance(raw, dict):
                commands.append(LocalProcessCommand.model_validate({"ref": ref, **raw}))
            elif isinstance(raw, list):
                commands.append(LocalProcessCommand(ref=ref, argv=[str(item) for item in raw]))
        return cls(commands)

    def get(self, ref: str) -> LocalProcessCommand | None:
        return self._commands.get(ref)


def local_process_decision(
    *,
    backend: SandboxBackend,
    request: LocalProcessRequest,
) -> LocalProcessDecision:
    """Evaluate whether a local process request preserves execution boundaries."""
    controls = ["policy_envelope", "capability_grant", "receipt", "redaction"]
    if backend.kind != "local_process" or backend.isolation_mode != "process":
        return _denied(
            request,
            "local process requests require a local_process backend with process isolation",
            controls,
        )
    if request.backend_id != backend.id:
        return _denied(request, f"request targets {request.backend_id}, not {backend.id}", controls)
    if not _supports_shell_execute(backend):
        return _denied(request, "backend does not declare shell.execute run support", controls)
    if not request.policy_envelope_id:
        return _denied(request, "local process execution requires a policy envelope", controls)
    if not request.capability_grant_id:
        return _denied(request, "local process execution requires a capability grant", controls)
    if not request.receipt_id:
        return _denied(request, "local process execution requires a receipt", controls)
    if _looks_like_inline_shell(request.command_ref):
        return _denied(
            request,
            "local process requests require command references, not inline shell",
            controls,
        )
    return LocalProcessDecision(
        status="allowed",
        allowed=True,
        reason="local process request is policy-, grant-, and receipt-bound",
        backend_id=backend.id,
        command_ref=request.command_ref,
        required_controls=controls,
    )


def execute_local_process_command(
    *,
    backend: SandboxBackend,
    request: LocalProcessRequest,
    registry: LocalProcessCommandRegistry,
    cancel_event: Event | None = None,
    poll_interval_seconds: float = 0.05,
) -> LocalProcessExecution:
    """Execute a registered command reference after local-process sandbox checks."""
    decision = local_process_decision(backend=backend, request=request)
    if not decision.allowed:
        return _execution_denied(request, decision.reason)
    command = registry.get(request.command_ref)
    if command is None:
        return _execution_denied(request, "command reference is not registered")
    deadline = time.monotonic() + command.timeout_seconds
    process = start_reviewed_local_process(
        command.argv,
        cwd=command.cwd,
        stdout="pipe",
        stderr="pipe",
    )
    while True:
        if cancel_event is not None and cancel_event.is_set():
            stdout, stderr = _terminate(process)
            return LocalProcessExecution(
                allowed=True,
                executed=True,
                reason="local process command cancelled",
                backend_id=request.backend_id,
                command_ref=request.command_ref,
                argv=command.argv,
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
                timeout_seconds=command.timeout_seconds,
                cancelled=True,
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            stdout, stderr = _terminate(process)
            return LocalProcessExecution(
                allowed=True,
                executed=True,
                reason="local process command timed out",
                backend_id=request.backend_id,
                command_ref=request.command_ref,
                argv=command.argv,
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
                timeout_seconds=command.timeout_seconds,
            )
        try:
            stdout, stderr = process.communicate(timeout=min(poll_interval_seconds, remaining))
            break
        except subprocess.TimeoutExpired:
            continue
    return LocalProcessExecution(
        allowed=True,
        executed=True,
        reason="local process command completed",
        backend_id=request.backend_id,
        command_ref=request.command_ref,
        argv=command.argv,
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
        timeout_seconds=command.timeout_seconds,
    )


def run_reviewed_local_process(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout_seconds: float = 30.0,
) -> LocalProcessExecution:
    """Run a fixed argv list through the reviewed local-process boundary."""
    process = start_reviewed_local_process(
        argv,
        cwd=cwd,
        env=env,
        stdout="pipe",
        stderr="pipe",
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        stdout, stderr = _terminate(process)
        return LocalProcessExecution(
            allowed=True,
            executed=True,
            reason="local process command timed out",
            backend_id="reviewed-local-process",
            command_ref=_command_ref(argv),
            argv=[str(arg) for arg in argv],
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timeout_seconds=timeout_seconds,
        )
    return LocalProcessExecution(
        allowed=True,
        executed=True,
        reason="local process command completed",
        backend_id="reviewed-local-process",
        command_ref=_command_ref(argv),
        argv=[str(arg) for arg in argv],
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
        timeout_seconds=timeout_seconds,
    )


def start_reviewed_local_process(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    stdin: int | IO[Any] | None = None,
    stdout: Literal["pipe"] | int | IO[Any] | None = None,
    stderr: Literal["pipe", "stdout"] | int | IO[Any] | None = None,
) -> subprocess.Popen[str]:
    """Start a fixed argv list without shell expansion."""
    if not argv:
        raise LocalProcessStartError("local process argv is required")
    if _looks_like_inline_shell(str(argv[0])):
        raise LocalProcessStartError("local process executable must be a resolved command path")
    stdout_target: int | IO[Any] | None = subprocess.PIPE if stdout == "pipe" else stdout
    stderr_target = (
        subprocess.PIPE
        if stderr == "pipe"
        else subprocess.STDOUT
        if stderr == "stdout"
        else stderr
    )
    stdin_target: int | IO[Any] = subprocess.DEVNULL if stdin is None else stdin
    try:
        return subprocess.Popen(  # nosec B603
            [str(arg) for arg in argv],
            cwd=str(cwd) if cwd is not None else None,
            env=dict(env) if env is not None else None,
            stdin=stdin_target,
            stdout=stdout_target,
            stderr=stderr_target,
            text=True,
        )
    except OSError as exc:
        raise LocalProcessStartError("local process command could not be executed") from exc


def _supports_shell_execute(backend: SandboxBackend) -> bool:
    return any(
        capability.name == "shell.execute" and "run" in capability.operations
        for capability in backend.capabilities
    )


def _execution_denied(request: LocalProcessRequest, reason: str) -> LocalProcessExecution:
    return LocalProcessExecution(
        allowed=False,
        executed=False,
        reason=reason,
        backend_id=request.backend_id,
        command_ref=request.command_ref,
    )


def _text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _command_ref(argv: Sequence[str]) -> str:
    return Path(str(argv[0])).name if argv else "unknown"


def _terminate(process: subprocess.Popen[str]) -> tuple[str, str]:
    process.terminate()
    try:
        stdout, stderr = process.communicate(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
    return stdout, stderr


def _looks_like_inline_shell(command_ref: str) -> bool:
    shell_tokens = (" ", "&&", "||", ";", "|", "$(", "`")
    return any(token in command_ref for token in shell_tokens)


def _denied(
    request: LocalProcessRequest,
    reason: str,
    controls: list[str],
) -> LocalProcessDecision:
    return LocalProcessDecision(
        status="denied",
        allowed=False,
        reason=reason,
        backend_id=request.backend_id,
        command_ref=request.command_ref,
        required_controls=controls,
    )
