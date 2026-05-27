"""Anthropic Claude CLI token export helpers."""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from craik.runtime.auth.profile import AuthProfile, CredentialKind, CredentialStatus
from craik.runtime.shell.credential_storage import put_cached_credential

CLAUDE_CODE_OAUTH_TOKEN_PATTERN = re.compile(r"sk-ant-oat[A-Za-z0-9._~+/=#-]+")
DEFAULT_CLAUDE_SETUP_TOKEN_COMMAND = ("claude", "setup-token")
DEFAULT_CLAUDE_AUTH_STATUS_COMMAND = ("claude", "auth", "status")


class AnthropicClaudeCliError(RuntimeError):
    """Raised when Claude CLI token export or storage fails."""


class CommandRunner(Protocol):
    """Minimal subprocess.run-compatible protocol."""

    def __call__(
        self,
        args: Sequence[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        """Run a command and return its completed process."""
        raise NotImplementedError


@dataclass(frozen=True)
class AnthropicClaudeCliLoginResult:
    """Redacted result for a Claude CLI token export login."""

    profile: AuthProfile
    status: CredentialStatus
    credential_storage_backend: str


def create_claude_cli_profile(
    *,
    profile_id: str = "anthropic:default",
    command: Sequence[str] = ("claude",),
) -> AnthropicClaudeCliLoginResult:
    """Create a marker profile that delegates Anthropic execution to Claude CLI."""
    executable = command[0] if command else "claude"
    if shutil.which(executable) is None:
        raise AnthropicClaudeCliError(
            "Claude CLI was not found. Install Anthropic Claude Code and run "
            "`claude` to authenticate before retrying."
        )
    now = datetime.now(UTC).isoformat()
    profile = AuthProfile(
        id=profile_id,
        kind=CredentialKind.MARKER,
        provider_family="anthropic",
        metadata={
            "billing_surface": "anthropic-claude-cli",
            "credential_backend": "claude-cli",
            "credential_mode": "oauth",
            "external_runtime": "claude-cli",
            "last_validated_at": now,
            "provider": "anthropic",
            "source": "claude-cli-external",
            "command": list(command),
        },
        created_at=datetime.now(UTC),
        last_status="ok",
    )
    return AnthropicClaudeCliLoginResult(
        profile=profile,
        status=CredentialStatus(status="ok"),
        credential_storage_backend="claude-cli",
    )


def extract_claude_code_oauth_token(text: str) -> str | None:
    """Extract a Claude Code OAuth token from shell export text or raw command output."""
    compact = "".join(text.split())
    match = CLAUDE_CODE_OAUTH_TOKEN_PATTERN.search(compact)
    return match.group(0) if match else None


def export_claude_code_oauth_token(
    *,
    runner: CommandRunner = subprocess.run,
    command: Sequence[str] = DEFAULT_CLAUDE_SETUP_TOKEN_COMMAND,
    timeout_seconds: float = 120.0,
) -> str:
    """Run `claude setup-token` and return the exported Claude Code OAuth token."""
    executable = command[0] if command else "claude"
    if shutil.which(executable) is None:
        raise AnthropicClaudeCliError(
            "Claude CLI was not found. Install Anthropic Claude Code, run "
            "`claude auth login`, then retry `craik auth login anthropic --mode=oauth`."
        )
    try:
        completed = runner(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        raise AnthropicClaudeCliError("Claude CLI setup-token timed out") from exc
    except OSError as exc:
        raise AnthropicClaudeCliError("Claude CLI setup-token failed to start") from exc

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    if completed.returncode != 0:
        detail = _safe_cli_output(output)
        raise AnthropicClaudeCliError(
            "Claude CLI setup-token failed"
            + (f": {detail}" if detail else ". Run `claude auth login` and retry.")
        )
    token = extract_claude_code_oauth_token(output)
    if token:
        return token
    raise AnthropicClaudeCliError(
        "Claude CLI setup-token did not print CLAUDE_CODE_OAUTH_TOKEN. "
        "Run `claude setup-token` manually and paste the token into "
        "`craik auth login anthropic --mode=oauth --no-browser`."
    )


def claude_cli_runtime_status(
    *,
    runner: CommandRunner = subprocess.run,
    command: Sequence[str] = DEFAULT_CLAUDE_AUTH_STATUS_COMMAND,
    timeout_seconds: float = 15.0,
) -> CredentialStatus:
    """Return whether the delegated local Claude CLI is authenticated."""
    executable = command[0] if command else "claude"
    if shutil.which(executable) is None:
        return CredentialStatus(status="rejected", detail="Claude CLI was not found")
    try:
        completed = runner(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (TimeoutError, OSError) as exc:
        return CredentialStatus(status="rejected", detail=str(exc))
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    if completed.returncode != 0:
        detail = _safe_cli_output(output) or "Claude CLI auth status failed"
        return CredentialStatus(status="rejected", detail=detail)
    if '"loggedIn": true' in output or '"loggedIn":true' in output:
        return CredentialStatus(status="ok")
    return CredentialStatus(status="rejected", detail="Claude CLI is not logged in")


def store_claude_cli_token_profile(
    token: str,
    *,
    profile_id: str = "anthropic:default",
    env: dict[str, str] | None = None,
) -> AnthropicClaudeCliLoginResult:
    """Store a Claude Code OAuth token as an Anthropic keyring-ref profile."""
    normalized = extract_claude_code_oauth_token(token) or token.strip()
    if not normalized.startswith("sk-ant-oat"):
        raise AnthropicClaudeCliError("Anthropic Claude CLI token must start with sk-ant-oat")
    ref = f"{profile_id}:claude-cli-token"
    storage_status = put_cached_credential(ref, normalized, env=env)
    now = datetime.now(UTC).isoformat()
    profile = AuthProfile(
        id=profile_id,
        kind=CredentialKind.KEYRING_REF,
        provider_family="anthropic",
        metadata={
            "base_url": "https://api.anthropic.com",
            "billing_surface": "anthropic-claude-cli",
            "credential_backend": storage_status.backend,
            "credential_mode": "oauth",
            "last_validated_at": now,
            "provider": "anthropic",
            "ref": ref,
            "source": "claude-cli-setup-token",
        },
        created_at=datetime.now(UTC),
        last_status="ok",
    )
    return AnthropicClaudeCliLoginResult(
        profile=profile,
        status=CredentialStatus(status="ok"),
        credential_storage_backend=storage_status.backend,
    )


def _safe_cli_output(output: str) -> str:
    redacted = CLAUDE_CODE_OAUTH_TOKEN_PATTERN.sub("[REDACTED]", " ".join(output.split()))
    return redacted[:300]


__all__ = [
    "AnthropicClaudeCliError",
    "AnthropicClaudeCliLoginResult",
    "claude_cli_runtime_status",
    "create_claude_cli_profile",
    "extract_claude_code_oauth_token",
    "export_claude_code_oauth_token",
    "store_claude_cli_token_profile",
]
