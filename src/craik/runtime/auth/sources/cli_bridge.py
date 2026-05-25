"""Credential source backed by a configured vendor CLI command."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, BinaryIO, Literal

from craik.runtime.auth.profile import CredentialStatus
from craik.runtime.providers.provider_transport import ProviderFamily

TokenExtractor = Literal["stdout_json", "stdout_line"]
MAX_CLI_BRIDGE_OUTPUT_BYTES = 1024 * 1024
CLI_BRIDGE_READ_CHUNK_BYTES = 16 * 1024


class CLIBridgeCredentialError(RuntimeError):
    """Raised when a CLI bridge cannot resolve credential material."""


@dataclass(frozen=True)
class CLIBridgeCredentialSource:
    """Resolve credentials by delegating to a configured local command."""

    command: tuple[str, ...]
    token_extractor: TokenExtractor
    key_path: tuple[str, ...] = ("token",)
    timeout_seconds: float = 5.0

    def headers_for(self, family: ProviderFamily) -> dict[str, str]:
        """Return provider-specific headers for a bridged credential."""
        token = self._resolve_token()
        if family == "anthropic":
            return {
                "Authorization": f"Bearer {token}",
                "anthropic-version": "2023-06-01",
            }
        if family == "gemini":
            return {"x-goog-api-key": token}
        return {"Authorization": f"Bearer {token}"}

    def status(self) -> CredentialStatus:
        """Check whether the bridge can resolve a token without exposing it."""
        try:
            self._resolve_token()
        except CLIBridgeCredentialError as exc:
            return CredentialStatus(status="rejected", detail=str(exc))
        return CredentialStatus(status="ok")

    def _resolve_token(self) -> str:
        stdout = self._command_stdout()
        if self.token_extractor == "stdout_line":
            token = next((line.strip() for line in stdout.splitlines() if line.strip()), "")
            if not token:
                raise CLIBridgeCredentialError("CLI bridge command produced no token")
            return token
        if self.token_extractor == "stdout_json":
            try:
                parsed = json.loads(stdout)
            except json.JSONDecodeError as exc:
                raise CLIBridgeCredentialError("CLI bridge command output was not JSON") from exc
            if not isinstance(parsed, dict):
                raise CLIBridgeCredentialError("CLI bridge command JSON was not an object")
            return _token_from_json(parsed, self.key_path)
        raise CLIBridgeCredentialError("unsupported CLI bridge token extractor")

    def _command_stdout(self) -> str:
        if not self.command:
            raise CLIBridgeCredentialError("CLI bridge command is empty")
        try:
            process = subprocess.Popen(
                list(self.command),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=False,
            )
        except OSError as exc:
            raise CLIBridgeCredentialError("CLI bridge command could not be executed") from exc
        if process.stdout is None:
            process.kill()
            raise CLIBridgeCredentialError("CLI bridge command could not be executed")

        stdout = bytearray()
        overflow = threading.Event()
        reader = threading.Thread(
            target=_read_bounded_stdout,
            args=(process.stdout, stdout, overflow),
            daemon=True,
        )
        reader.start()
        deadline = time.monotonic() + self.timeout_seconds
        while process.poll() is None:
            if overflow.is_set():
                process.kill()
                process.wait()
                reader.join(timeout=1)
                raise CLIBridgeCredentialError("CLI bridge command produced too much output")
            if time.monotonic() >= deadline:
                process.kill()
                process.wait()
                reader.join(timeout=1)
                raise CLIBridgeCredentialError("CLI bridge command timed out")
            time.sleep(0.01)
        reader.join(timeout=1)
        if overflow.is_set():
            raise CLIBridgeCredentialError("CLI bridge command produced too much output")
        if process.returncode != 0:
            raise CLIBridgeCredentialError("CLI bridge command failed")
        return bytes(stdout).decode("utf-8", errors="replace")


def _read_bounded_stdout(
    pipe: BinaryIO,
    stdout: bytearray,
    overflow: threading.Event,
) -> None:
    while True:
        chunk = pipe.read(CLI_BRIDGE_READ_CHUNK_BYTES)
        if not chunk:
            return
        if len(stdout) + len(chunk) > MAX_CLI_BRIDGE_OUTPUT_BYTES:
            overflow.set()
            return
        stdout.extend(chunk)


def _token_from_json(payload: dict[str, Any], key_path: tuple[str, ...]) -> str:
    current: Any = payload
    for key in key_path:
        if not isinstance(current, dict):
            raise CLIBridgeCredentialError("CLI bridge token path did not resolve")
        current = current.get(key)
    if not isinstance(current, str) or not current:
        raise CLIBridgeCredentialError("CLI bridge token path did not resolve")
    return current
