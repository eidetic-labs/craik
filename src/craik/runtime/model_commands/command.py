"""Structured model command implementations."""

from __future__ import annotations

from craik.runtime.auth import AuthProfileStore
from craik.runtime.auth.visibility import active_operator_session_from_env, visible_auth_profiles
from craik.runtime.contract import CommandResult, NextAction
from craik.runtime.modeling import (
    ModelSettings,
    ModelSettingsStore,
    model_profile_from_ref,
)
from craik.runtime.shell.readiness import resolve_readiness


def model_list_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return configured provider/model choices and visible auth profiles."""
    settings = ModelSettingsStore.from_env(env).load()
    try:
        auth_profiles = [
            {
                "id": profile.id,
                "provider_family": profile.provider_family,
                "last_status": profile.last_status,
            }
            for profile in visible_auth_profiles(
                AuthProfileStore.from_env(env).list(), active_operator_session_from_env(env)
            )
        ]
    except Exception:
        auth_profiles = []
    return CommandResult(
        payload={
            "active_model": settings.active_model,
            "active_profile_id": settings.active_profile_id,
            "active_profile": (
                settings.active_profile.as_dict() if settings.active_profile is not None else None
            ),
            "profiles": {key: profile.as_dict() for key, profile in settings.profiles.items()},
            "aliases": settings.aliases,
            "fallbacks": settings.fallbacks,
            "configured_profiles": auth_profiles,
        },
        shape="kv",
        next_actions=[
            NextAction(
                text="run /model set <provider/model>",
                command="/model set",
                field="active_model",
            )
        ]
        if settings.active_model is None
        else [],
    )


def model_status_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return active model state and readiness."""
    settings = ModelSettingsStore.from_env(env).load()
    readiness = resolve_readiness(env)
    return CommandResult(
        payload={
            "active_model": settings.active_model,
            "active_profile_id": settings.active_profile_id,
            "active_profile": (
                settings.active_profile.as_dict() if settings.active_profile is not None else None
            ),
            "readiness": readiness.as_dict(),
            "aliases": settings.aliases,
            "fallbacks": settings.fallbacks,
        },
        shape="kv",
    )


def model_set_result(
    model: str,
    env: dict[str, str] | None = None,
    *,
    display_name: str | None = None,
    backend: str = "provider",
    options: dict[str, object] | None = None,
) -> CommandResult:
    """Persist and return the active model selection."""
    validate_model_ref(model)
    store = ModelSettingsStore.from_env(env)
    settings = store.load()
    profile = model_profile_from_ref(
        model,
        display_name=display_name,
        backend=backend,
        options=options,
    )
    profiles = {**settings.profiles, profile.id: profile}
    updated = ModelSettings(
        active_model=model,
        active_profile_id=profile.id,
        profiles=profiles,
        aliases=settings.aliases,
        fallbacks=settings.fallbacks,
    )
    store.save(updated)
    return CommandResult(payload=updated.as_dict(), shape="kv")


def model_effort_result(
    effort: str | None = None, env: dict[str, str] | None = None
) -> CommandResult:
    """Inspect or update reasoning effort for the active model profile."""
    store = ModelSettingsStore.from_env(env)
    settings = store.load()
    profile = settings.active_profile
    if settings.active_model is None or profile is None:
        raise ValueError("effort requires an active model; run /model set <provider/model> first")
    if effort is None:
        current = _profile_effort(profile.options)
        return CommandResult(
            payload={
                "active_model": settings.active_model,
                "active_profile_id": settings.active_profile_id,
                "reasoning_effort": current,
                "active_profile": profile.as_dict(),
            },
            shape="kv",
        )
    normalized = _normalize_effort(effort)
    options = dict(profile.options)
    if normalized == "default":
        options.pop("reasoning_effort", None)
    else:
        options["reasoning_effort"] = normalized
    updated_profile = model_profile_from_ref(
        settings.active_model,
        backend=profile.backend,
        options=options,
    )
    profiles = {**settings.profiles, updated_profile.id: updated_profile}
    updated = ModelSettings(
        active_model=settings.active_model,
        active_profile_id=updated_profile.id,
        profiles=profiles,
        aliases=settings.aliases,
        fallbacks=settings.fallbacks,
    )
    store.save(updated)
    return CommandResult(
        payload={
            **updated.as_dict(),
            "reasoning_effort": normalized,
            "active_profile": updated_profile.as_dict(),
        },
        shape="kv",
    )


def model_probe_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return model readiness without sending live prompts."""
    settings = ModelSettingsStore.from_env(env).load()
    readiness = resolve_readiness(env)
    return CommandResult(
        payload={
            "active_model": settings.active_model,
            "active_profile_id": settings.active_profile_id,
            "active_profile": (
                settings.active_profile.as_dict() if settings.active_profile is not None else None
            ),
            "can_execute": readiness.state == "fully-ready" and settings.active_model is not None,
            "state": readiness.state,
            "missing": readiness.missing,
        },
        shape="kv",
    )


def model_alias_result(
    action: str,
    name: str | None = None,
    target: str | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """List, add, or remove model aliases."""
    store = ModelSettingsStore.from_env(env)
    settings = store.load()
    aliases = dict(settings.aliases)
    if action == "list":
        return CommandResult(payload=aliases, shape="kv")
    if action == "add" and name and target:
        validate_model_ref(target)
        aliases[name] = target
    elif action == "remove" and name:
        aliases.pop(name, None)
    else:
        raise ValueError("expected alias list, alias add <name> <target>, or alias remove <name>")
    updated = ModelSettings(
        settings.active_model,
        settings.active_profile_id,
        settings.profiles,
        aliases,
        settings.fallbacks,
    )
    store.save(updated)
    return CommandResult(payload=updated.as_dict(), shape="kv")


def model_fallback_result(
    action: str,
    model: str | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """List, add, remove, or clear model fallback order."""
    store = ModelSettingsStore.from_env(env)
    settings = store.load()
    fallbacks = list(settings.fallbacks)
    if action == "list":
        return CommandResult(payload=fallbacks, shape="table")
    if action == "add" and model:
        validate_model_ref(model)
        fallbacks = [item for item in fallbacks if item != model]
        fallbacks.append(model)
    elif action == "remove" and model:
        fallbacks = [item for item in fallbacks if item != model]
    elif action == "clear":
        fallbacks = []
    else:
        raise ValueError("expected fallback list, add <model>, remove <model>, or clear")
    updated = ModelSettings(
        settings.active_model,
        settings.active_profile_id,
        settings.profiles,
        settings.aliases,
        fallbacks,
    )
    store.save(updated)
    return CommandResult(payload=updated.as_dict(), shape="kv")


def validate_model_ref(value: str) -> None:
    """Validate a provider/model selector."""
    if "/" not in value or value.startswith("/") or value.endswith("/"):
        raise ValueError("model reference must be formatted as <provider>/<model>")


def parse_model_options(
    *,
    reasoning_effort: str | None = None,
    service_tier: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    passthrough: list[str] | None = None,
) -> dict[str, object]:
    """Parse common and provider-specific model profile options."""
    options: dict[str, object] = {}
    if reasoning_effort is not None:
        options["reasoning_effort"] = reasoning_effort
    if service_tier is not None:
        options["service_tier"] = service_tier
    if temperature is not None:
        options["temperature"] = temperature
    if max_output_tokens is not None:
        options["max_output_tokens"] = max_output_tokens
    for item in passthrough or []:
        if "=" not in item:
            raise ValueError("--option must be formatted as key=value")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("--option key must not be empty")
        options[key] = _coerce_option_value(value.strip())
    return options


def _profile_effort(options: dict[str, object]) -> str:
    effort = options.get("reasoning_effort")
    return effort if isinstance(effort, str) and effort.strip() else "default"


def _normalize_effort(effort: str) -> str:
    normalized = effort.strip()
    if normalized in {"default", "low", "medium", "high", "max"}:
        return normalized
    raise ValueError("effort must be one of default, low, medium, high, or max")


def _coerce_option_value(value: str) -> object:
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none"}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
