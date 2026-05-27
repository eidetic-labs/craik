"""Anthropic environment credential resolution helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

CLAUDE_CODE_OAUTH_TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"  # nosec B105 - env var name, not a secret.
ANTHROPIC_TOKEN_ENV = "ANTHROPIC_TOKEN"  # nosec B105 - env var name, not a secret.
ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"
CRAIK_ANTHROPIC_API_KEY_ENV = "CRAIK_ANTHROPIC_API_KEY"
CLAUDE_CODE_VERSION = "2.1.75"
CLAUDE_CODE_BETA_HEADER = "claude-code-20250219,oauth-2025-04-20"


@dataclass(frozen=True, slots=True)
class AnthropicCredential:
    """Resolved Anthropic credential and display-safe source metadata."""

    token: str
    source: str
    display: str


def resolve_anthropic_credential_from_env(
    env: Mapping[str, str] | None = None,
    *,
    fallback_env_vars: tuple[str, ...] = (
        ANTHROPIC_TOKEN_ENV,
        ANTHROPIC_API_KEY_ENV,
        CRAIK_ANTHROPIC_API_KEY_ENV,
    ),
) -> AnthropicCredential | None:
    """Resolve Anthropic credentials from documented environment variables."""
    source_env = env if env is not None else os.environ
    claude_code_token = _env_value(source_env, CLAUDE_CODE_OAUTH_TOKEN_ENV)
    if claude_code_token:
        return AnthropicCredential(
            token=claude_code_token,
            source="env:CLAUDE_CODE_OAUTH_TOKEN",
            display="Anthropic CLI OAuth token (env)",
        )
    for env_var in fallback_env_vars:
        api_key = _env_value(source_env, env_var)
        if api_key:
            return AnthropicCredential(
                token=api_key,
                source=f"env:{env_var}",
                display=f"{env_var} (env)",
            )
    return None


def is_claude_code_oauth_token(value: str) -> bool:
    """Return whether a value looks like Anthropic's Claude Code OAuth token."""
    return value.strip().startswith("sk-ant-oat")


def anthropic_headers_for_credential(
    credential: str,
    *,
    credential_mode: str | None = None,
) -> dict[str, str]:
    """Return Anthropic request headers for either API keys or Claude Code tokens."""
    token = credential.strip()
    headers = {"anthropic-version": "2023-06-01"}
    if not token:
        return headers
    if credential_mode == "claude-cli" or is_claude_code_oauth_token(token):
        return headers | {
            "Authorization": f"Bearer {token}",
            "anthropic-beta": CLAUDE_CODE_BETA_HEADER,
            "user-agent": f"claude-cli/{CLAUDE_CODE_VERSION}",
            "x-app": "cli",
        }
    return headers | {"x-api-key": token}


def _env_value(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "")
    return value.strip()
