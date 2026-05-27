"""Context-aware slash command completion for the terminal UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from craik.runtime.auth.guided_setup import GUIDED_PROVIDER_DEFAULTS
from craik.runtime.auth.login import auth_status_payload
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.modeling import ModelSettingsStore
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.providers.model_providers import default_model_provider_registry
from craik.runtime.shell.contract_runtime.registry_provider import get_tui_registry
from craik.runtime.store import DATABASE_NAME, LocalStore


@dataclass(frozen=True)
class CompletionCandidate:
    """One completion candidate and its operator-facing description."""

    value: str
    description: str = ""


def complete_slash_input(
    text: str,
    *,
    env: dict[str, str] | None = None,
    registry: AutoSlashRegistry | None = None,
) -> list[CompletionCandidate]:
    """Return command or argument completions for a slash input buffer."""
    if registry is None:
        registry = get_tui_registry()
    if not text.startswith("/"):
        return []
    if text.endswith(" "):
        tokens = text.strip().split()
        partial = ""
    else:
        tokens = text.strip().split()
        partial = tokens[-1] if len(tokens) > 1 else text.removeprefix("/")
    command = tokens[0].removeprefix("/") if tokens else ""
    if len(tokens) <= 1 and not text.endswith(" "):
        return [
            candidate
            for candidate in _command_candidates(registry)
            if candidate.value.removeprefix("/").startswith(partial)
        ]
    if command in {"auth", "provider"} and len(tokens) >= 2 and tokens[1] == "login":
        return _filter_candidates(
            [
                CompletionCandidate(provider, "provider credential profile")
                for provider in sorted(GUIDED_PROVIDER_DEFAULTS)
            ],
            partial,
        )
    if command == "model" and len(tokens) >= 2 and tokens[1] == "set":
        return _filter_candidates(_model_candidates(env), partial)
    if command in {"resume", "sessions"}:
        return _filter_candidates(_session_candidates(env), partial)
    if command == "approvals" and len(tokens) >= 2 and tokens[1] == "decide":
        return _filter_candidates(_approval_candidates(env), partial)
    if command == "auth" and len(tokens) >= 2 and tokens[1] == "status":
        return _filter_candidates(_auth_profile_candidates(env), partial)
    return []


def _model_candidates(env: dict[str, str] | None) -> list[CompletionCandidate]:
    settings = ModelSettingsStore.from_env(env).load()
    candidates = [
        CompletionCandidate(alias, f"alias for {target}")
        for alias, target in sorted(settings.aliases.items())
    ]
    for provider in default_model_provider_registry().list():
        default_model = provider.metadata.get("default_model")
        if isinstance(default_model, str):
            candidates.append(
                CompletionCandidate(
                    f"{provider.provider}/{default_model}",
                    f"default model for {provider.provider}",
                )
            )
    return candidates


def _command_candidates(registry: AutoSlashRegistry) -> list[CompletionCandidate]:
    candidates: dict[str, CompletionCandidate] = {}
    for spec in registry.slash_specs:
        value = spec.name
        if "-" in value.removeprefix("/"):
            value = "/" + value.removeprefix("/").split("-", 1)[0]
        candidates.setdefault(value, CompletionCandidate(value, spec.summary))
    return [candidates[value] for value in sorted(candidates)]


def _session_candidates(env: dict[str, str] | None) -> list[CompletionCandidate]:
    sessions = _store_list(env, "list_agent_session_states")
    return [
        CompletionCandidate(str(session.id), str(getattr(session, "status", "")))
        for session in sessions
        if getattr(session, "id", None)
    ]


def _approval_candidates(env: dict[str, str] | None) -> list[CompletionCandidate]:
    approvals = [
        item
        for item in _store_list(env, "list_human_delegations")
        if getattr(item, "kind", None) == "approval"
        and getattr(item, "status", None) == "open"
    ]
    return [
        CompletionCandidate(str(item.id), str(getattr(item, "summary", "")))
        for item in approvals
        if getattr(item, "id", None)
    ]


def _auth_profile_candidates(env: dict[str, str] | None) -> list[CompletionCandidate]:
    try:
        rows = auth_status_payload(env)
    except Exception:
        return []
    return [
        CompletionCandidate(str(row["id"]), str(row.get("health_status", "")))
        for row in rows
        if "id" in row
    ]


def _store_list(env: dict[str, str] | None, method_name: str) -> list[Any]:
    paths = resolve_craik_paths(env)
    if not (paths.state / DATABASE_NAME).exists():
        return []
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        method = getattr(store, method_name, None)
        if method is None:
            return []
        return list(method())
    finally:
        store.close()


def _filter_candidates(
    candidates: list[CompletionCandidate],
    partial: str,
) -> list[CompletionCandidate]:
    normalized = partial.strip()
    if not normalized:
        return candidates
    return [candidate for candidate in candidates if candidate.value.startswith(normalized)]
