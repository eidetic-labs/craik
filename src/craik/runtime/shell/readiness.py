"""Progressive setup readiness for the Craik agent shell."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from craik.runtime.auth import AuthProfileStore, AuthProfileStoreError
from craik.runtime.auth.operator import OperatorSessionNotFoundError, OperatorSessionStore
from craik.runtime.paths import CraikPaths, resolve_craik_paths
from craik.runtime.store import DATABASE_NAME

ReadinessState = Literal[
    "unconfigured",
    "fixture",
    "local-model",
    "operator-only",
    "provider-only",
    "fully-ready",
    "restricted/offline",
]


@dataclass(frozen=True)
class ReadinessReport:
    """Current launch readiness and actionable setup hints."""

    state: ReadinessState
    home: Path
    initialized: bool
    operator_authenticated: bool
    provider_configured: bool
    local_model_configured: bool
    active_profile: str
    active_model: str | None = None
    missing: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable readiness payload."""
        return {
            "state": self.state,
            "home": str(self.home),
            "initialized": self.initialized,
            "operator_authenticated": self.operator_authenticated,
            "provider_configured": self.provider_configured,
            "local_model_configured": self.local_model_configured,
            "active_profile": self.active_profile,
            "active_model": self.active_model,
            "missing": self.missing,
            "next_actions": self.next_actions,
            "warnings": self.warnings,
        }


def resolve_readiness(env: dict[str, str] | None = None) -> ReadinessReport:
    """Resolve Craik's progressive setup state without requiring authentication."""
    values = dict(os.environ) if env is None else env
    paths = resolve_craik_paths(values)
    initialized = _home_initialized(paths)
    operator_authenticated = _operator_authenticated(values)
    auth_profiles = _auth_profile_ids(values)
    provider_configured = bool(auth_profiles)
    local_model_configured = any(_is_local_profile(profile_id) for profile_id in auth_profiles)
    active_profile = values.get("CRAIK_PROFILE", "default")
    active_model = _active_model(paths)

    if values.get("CRAIK_OFFLINE") == "1":
        state: ReadinessState = "restricted/offline"
    elif not initialized and not provider_configured and not operator_authenticated:
        state = "unconfigured"
    elif values.get("CRAIK_FIXTURE") == "1":
        state = "fixture"
    elif local_model_configured and not operator_authenticated:
        state = "local-model"
    elif operator_authenticated and provider_configured:
        state = "fully-ready"
    elif operator_authenticated:
        state = "operator-only"
    elif provider_configured:
        state = "provider-only"
    else:
        state = "unconfigured"

    missing: list[str] = []
    if not operator_authenticated:
        missing.append("operator session")
    if not provider_configured:
        missing.append("provider credentials")
    if active_model is None:
        missing.append("active model")

    next_actions = _next_actions(
        state,
        operator_authenticated=operator_authenticated,
        provider_configured=provider_configured,
        active_model=active_model,
    )
    warnings = ["restricted/offline mode is active"] if state == "restricted/offline" else []
    return ReadinessReport(
        state=state,
        home=paths.home,
        initialized=initialized,
        operator_authenticated=operator_authenticated,
        provider_configured=provider_configured,
        local_model_configured=local_model_configured,
        active_profile=active_profile,
        active_model=active_model,
        missing=missing,
        next_actions=next_actions,
        warnings=warnings,
    )


def readiness_allows_action(report: ReadinessReport, requirement: str) -> tuple[bool, str | None]:
    """Return whether a slash command can run under the current readiness report."""
    if requirement == "none":
        return True, None
    if requirement == "operator" and report.operator_authenticated:
        return True, None
    if requirement == "provider" and report.provider_configured:
        return True, None
    if requirement == "model" and report.active_model:
        return True, None
    if requirement == "ready" and report.state == "fully-ready":
        return True, None
    return False, f"blocked: requires {requirement}; missing {', '.join(report.missing) or 'setup'}"


def _home_initialized(paths: CraikPaths) -> bool:
    return paths.home.exists() and (paths.state / DATABASE_NAME).exists()


def _operator_authenticated(env: dict[str, str]) -> bool:
    try:
        OperatorSessionStore.from_env(env).get()
    except OperatorSessionNotFoundError:
        return False
    return True


def _auth_profile_ids(env: dict[str, str]) -> list[str]:
    try:
        return [profile.id for profile in AuthProfileStore.from_env(env).list()]
    except AuthProfileStoreError:
        return []


def _is_local_profile(profile_id: str) -> bool:
    return profile_id == "local" or profile_id.startswith("local:")


def _active_model(paths: CraikPaths) -> str | None:
    model_path = paths.config / "model-settings.json"
    if not model_path.exists():
        return None
    try:
        import json

        payload = json.loads(model_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = payload.get("active_model")
    return value if isinstance(value, str) and value.strip() else None


def _next_actions(
    state: ReadinessState,
    *,
    operator_authenticated: bool,
    provider_configured: bool,
    active_model: str | None,
) -> list[str]:
    if state == "restricted/offline":
        return ["unset CRAIK_OFFLINE=1 to use remote providers", "run /status for local options"]
    actions: list[str] = []
    if not operator_authenticated:
        actions.append("run /auth login or craik auth login")
    if not provider_configured:
        actions.append("run /provider login openai, anthropic, gemini, or local")
    if active_model is None:
        actions.append("run /model set <provider/model>")
    if not actions:
        actions.append("start with a prompt or run /help")
    return actions
