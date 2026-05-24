"""Progressive setup readiness for the Craik agent shell."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from craik.runtime.auth import AuthProfileStore, AuthProfileStoreError
from craik.runtime.auth.login import profile_runtime_status
from craik.runtime.auth.operator import (
    OperatorSession,
    OperatorSessionNotFoundError,
    OperatorSessionStore,
)
from craik.runtime.auth.operator_modes import operator_session_required
from craik.runtime.auth.visibility import visible_auth_profiles
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
    operator_required: bool
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
            "operator_required": self.operator_required,
            "operator_authenticated": self.operator_authenticated,
            "provider_configured": self.provider_configured,
            "local_model_configured": self.local_model_configured,
            "active_profile": self.active_profile,
            "active_model": self.active_model,
            "missing": self.missing,
            "next_actions": self.next_actions,
            "warnings": self.warnings,
        }


def resolve_readiness(
    env: dict[str, str] | None = None,
    *,
    in_tui: bool = False,
) -> ReadinessReport:
    """Resolve Craik's progressive setup state without requiring authentication."""
    values = dict(os.environ) if env is None else env
    paths = resolve_craik_paths(values)
    initialized = _home_initialized(paths)
    operator_session = _operator_session(values)
    operator_required = operator_session_required(values)
    operator_authenticated = operator_session is not None
    auth_profiles = _auth_profile_ids(values, operator_session=operator_session)
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
    elif local_model_configured and not operator_authenticated and operator_required:
        state = "local-model"
    elif provider_configured and active_model is not None and (
        operator_authenticated or not operator_required
    ):
        state = "fully-ready"
    elif operator_authenticated:
        state = "operator-only"
    elif provider_configured:
        state = "provider-only"
    else:
        state = "unconfigured"

    missing: list[str] = []
    if operator_required and not operator_authenticated:
        missing.append("operator session")
    if not provider_configured:
        missing.append("provider credentials")
    if active_model is None:
        missing.append("active model")

    next_actions = _next_actions_for_state(
        state,
        operator_required=operator_required,
        operator_authenticated=operator_authenticated,
        provider_configured=provider_configured,
        active_model=active_model,
        in_tui=in_tui,
    )
    warnings = ["restricted/offline mode is active"] if state == "restricted/offline" else []
    return ReadinessReport(
        state=state,
        home=paths.home,
        initialized=initialized,
        operator_required=operator_required,
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


def next_actions(report: ReadinessReport, *, in_tui: bool) -> list[str]:
    """Return setup actions rendered for the TUI or outer CLI context."""
    return _next_actions_for_state(
        report.state,
        operator_required=report.operator_required,
        operator_authenticated=report.operator_authenticated,
        provider_configured=report.provider_configured,
        active_model=report.active_model,
        in_tui=in_tui,
    )


def _home_initialized(paths: CraikPaths) -> bool:
    return paths.home.exists() and (paths.state / DATABASE_NAME).exists()


def _operator_session(env: dict[str, str]) -> OperatorSession | None:
    try:
        return OperatorSessionStore.from_env(env).get()
    except OperatorSessionNotFoundError:
        return None


def _auth_profile_ids(
    env: dict[str, str],
    *,
    operator_session: OperatorSession | None = None,
) -> list[str]:
    try:
        profiles = AuthProfileStore.from_env(env).list()
    except AuthProfileStoreError:
        return []
    visible = visible_auth_profiles(profiles, operator_session)
    return [
        profile.id
        for profile in visible
        if profile_runtime_status(profile, env=env).status in {"ok", "unknown"}
    ]


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


def _next_actions_for_state(
    state: ReadinessState,
    *,
    operator_required: bool,
    operator_authenticated: bool,
    provider_configured: bool,
    active_model: str | None,
    in_tui: bool,
) -> list[str]:
    if state == "restricted/offline":
        return [
            "unset CRAIK_OFFLINE=1 to use remote providers",
            "use `/status` for local options" if in_tui else "run `craik status` for local options",
        ]
    actions: list[str] = []
    if operator_required and not operator_authenticated:
        actions.append("use `/login`" if in_tui else "run craik login")
    if not provider_configured:
        actions.append(
            "use `/auth login <provider>`"
            if in_tui
            else "run craik auth login <provider>"
        )
    if active_model is None:
        actions.append(
            "use `/model set <provider/model>`"
            if in_tui
            else "run craik model set <provider/model>"
        )
    if not actions:
        actions.append("start with a prompt or use `/help`" if in_tui else "run `craik --help`")
    return actions
