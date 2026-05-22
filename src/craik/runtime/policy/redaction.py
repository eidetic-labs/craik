"""Shared redaction utilities for persistence boundaries."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

REDACTION = "[REDACTED]"
SECRET_KEY_PARTS = ("secret", "token", "password", "api_key", "apikey", "credential")
NON_SECRET_KEYS = frozenset(
    {
        "allowed_credential_kinds",
        "allowed_credential_profiles",
        "estimated_tokens",
        "max_tokens",
        "provider_token_budget",
        "provider_token_budget_remaining",
        "provider_tokens_used",
        "secrets_in_config_allowed",
    }
)
REDACTED_VALUES = ("[REDACTED]", "<redacted>", "redacted")
REDACTED_VALUE_KEYS = frozenset(value.lower() for value in REDACTED_VALUES)

DEFAULT_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)\b(api[_-]?key|token|password|secret)=([^\s&]+)"),
    re.compile(r"(?i)(--(?:api[_-]?key|token|password|secret)(?:=|\s+))([^\s]+)"),
    re.compile(r"(?i)\b(ghp|github_pat|sk|xox[baprs])-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)(https?://)([^/\s:@]+):([^@\s/]+)@"),
    re.compile(r"(?i)(https?://)([A-Za-z0-9._~+/=-]{8,})@"),
)


@dataclass(frozen=True)
class RedactionConfig:
    """Configuration for redacting sensitive values."""

    patterns: tuple[re.Pattern[str], ...] = DEFAULT_SECRET_PATTERNS
    secret_key_parts: tuple[str, ...] = SECRET_KEY_PARTS
    replacement: str = REDACTION


@dataclass(frozen=True)
class RedactionResult:
    """Redacted payload plus whether anything changed."""

    value: Any
    redacted: bool = False
    redacted_paths: tuple[str, ...] = field(default_factory=tuple)


def redact(value: Any, config: RedactionConfig | None = None) -> RedactionResult:
    """Redact strings and structured payloads recursively."""
    active = config or RedactionConfig()
    redacted_paths: list[str] = []
    redacted_value = _redact_value(value, active, "$", redacted_paths, key_hint=None)
    return RedactionResult(
        value=redacted_value,
        redacted=bool(redacted_paths),
        redacted_paths=tuple(redacted_paths),
    )


def redaction_config_for_patterns(patterns: list[str]) -> RedactionConfig:
    """Extend default redaction with caller-provided regex patterns."""
    compiled = tuple(re.compile(pattern) for pattern in patterns)
    return RedactionConfig(patterns=(*DEFAULT_SECRET_PATTERNS, *compiled))


def contains_unredacted_secret(value: Any, config: RedactionConfig | None = None) -> bool:
    """Return whether a value appears to contain unredacted secret material."""
    return redact(value, config).redacted


def is_redacted_value(value: Any) -> bool:
    """Return whether a value is already visibly redacted."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.lower() in REDACTED_VALUE_KEYS
    return False


def _redact_value(
    value: Any,
    config: RedactionConfig,
    path: str,
    redacted_paths: list[str],
    *,
    key_hint: str | None,
) -> Any:
    if _is_secret_key(key_hint, config) and not is_redacted_value(value):
        redacted_paths.append(path)
        return config.replacement

    if isinstance(value, str):
        return _redact_string(value, config, path, redacted_paths)
    if isinstance(value, dict):
        return {
            key: _redact_value(
                item,
                config,
                f"{path}.{key}",
                redacted_paths,
                key_hint=str(key),
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _redact_value(
                item,
                config,
                f"{path}[{index}]",
                redacted_paths,
                key_hint=None,
            )
            for index, item in enumerate(value)
        ]
    if isinstance(value, tuple):
        return tuple(
            _redact_value(
                item,
                config,
                f"{path}[{index}]",
                redacted_paths,
                key_hint=None,
            )
            for index, item in enumerate(value)
        )
    return value


def _redact_string(
    value: str,
    config: RedactionConfig,
    path: str,
    redacted_paths: list[str],
) -> str:
    redacted = value
    for pattern in config.patterns:
        redacted = pattern.sub(_replacement_for_match(config), redacted)
    if redacted != value:
        redacted_paths.append(path)
    return redacted


def _replacement_for_match(config: RedactionConfig) -> Callable[[re.Match[str]], str]:
    def replace(match: re.Match[str]) -> str:
        if match.re.pattern.startswith("(?i)(https?://)"):
            if len(match.groups()) >= 3:
                return f"{match.group(1)}{config.replacement}:{config.replacement}@"
            return f"{match.group(1)}{config.replacement}@"
        if match.re.pattern.startswith("(?i)(--"):
            return f"{match.group(1)}{config.replacement}"
        if len(match.groups()) >= 2 and match.group(1).lower() in {
            "api_key",
            "apikey",
            "api-key",
            "token",
            "password",
            "secret",
        }:
            return f"{match.group(1)}={config.replacement}"
        if match.group(0).lower().startswith("bearer "):
            return f"Bearer {config.replacement}"
        return config.replacement

    return replace


def _is_secret_key(key: str | None, config: RedactionConfig) -> bool:
    if key is None:
        return False
    lowered = key.lower()
    if lowered in NON_SECRET_KEYS:
        return False
    return any(part in lowered for part in config.secret_key_parts)
