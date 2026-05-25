"""Anthropic environment credential resolution helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

CLAUDE_CODE_OAUTH_TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"  # nosec B105 - env var name, not a secret.
ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"
CRAIK_ANTHROPIC_API_KEY_ENV = "CRAIK_ANTHROPIC_API_KEY"

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


def _env_value(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "")
    return value.strip()
