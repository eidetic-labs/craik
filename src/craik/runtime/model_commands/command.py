"""Structured model command implementations."""

from __future__ import annotations

from craik.runtime.auth import AuthProfileStore
from craik.runtime.auth.visibility import active_operator_session_from_env, visible_auth_profiles
from craik.runtime.contract import CommandResult, NextAction
from craik.runtime.shell.model_settings import ModelSettings, ModelSettingsStore
from craik.runtime.shell.readiness import resolve_readiness


def model_list_result() -> CommandResult:
    """Return configured provider/model choices and visible auth profiles."""
    settings = ModelSettingsStore.from_env().load()
    try:
        auth_profiles = [
            {
                "id": profile.id,
                "provider_family": profile.provider_family,
                "last_status": profile.last_status,
            }
            for profile in visible_auth_profiles(
                AuthProfileStore.from_env().list(), active_operator_session_from_env()
            )
        ]
    except Exception:
        auth_profiles = []
    return CommandResult(
        payload={
            "active_model": settings.active_model,
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


def model_status_result() -> CommandResult:
    """Return active model state and readiness."""
    settings = ModelSettingsStore.from_env().load()
    readiness = resolve_readiness()
    return CommandResult(
        payload={
            "active_model": settings.active_model,
            "readiness": readiness.as_dict(),
            "aliases": settings.aliases,
            "fallbacks": settings.fallbacks,
        },
        shape="kv",
    )


def model_set_result(model: str) -> CommandResult:
    """Persist and return the active model selection."""
    validate_model_ref(model)
    store = ModelSettingsStore.from_env()
    settings = store.load()
    updated = ModelSettings(
        active_model=model,
        aliases=settings.aliases,
        fallbacks=settings.fallbacks,
    )
    store.save(updated)
    return CommandResult(payload=updated.as_dict(), shape="kv")


def model_probe_result() -> CommandResult:
    """Return model readiness without sending live prompts."""
    settings = ModelSettingsStore.from_env().load()
    readiness = resolve_readiness()
    return CommandResult(
        payload={
            "active_model": settings.active_model,
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
) -> CommandResult:
    """List, add, or remove model aliases."""
    store = ModelSettingsStore.from_env()
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
    updated = ModelSettings(settings.active_model, aliases, settings.fallbacks)
    store.save(updated)
    return CommandResult(payload=updated.as_dict(), shape="kv")


def model_fallback_result(action: str, model: str | None = None) -> CommandResult:
    """List, add, remove, or clear model fallback order."""
    store = ModelSettingsStore.from_env()
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
    updated = ModelSettings(settings.active_model, settings.aliases, fallbacks)
    store.save(updated)
    return CommandResult(payload=updated.as_dict(), shape="kv")


def validate_model_ref(value: str) -> None:
    """Validate a provider/model selector."""
    if "/" not in value or value.startswith("/") or value.endswith("/"):
        raise ValueError("model reference must be formatted as <provider>/<model>")
