"""Structured auth command implementations shared by CLI and slash commands."""

from __future__ import annotations

from craik.runtime.auth.login import auth_status_payload
from craik.runtime.contract import CommandResult
from craik.runtime.shell.readiness import resolve_readiness


def auth_summary_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return operator and provider auth readiness."""
    report = resolve_readiness(env)
    return CommandResult(
        payload={
            "operator_authenticated": report.operator_authenticated,
            "operator_required": report.operator_required,
            "profiles": auth_status_payload(env),
        },
        shape="table",
    )


def auth_status_result(env: dict[str, str] | None = None) -> CommandResult:
    """Return visible auth profile status rows."""
    return CommandResult(payload=auth_status_payload(env), shape="table")


def auth_logout_confirmation_result(
    profile_id: str | None = None,
    *,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Return a confirmation payload for credential-profile logout."""
    report = resolve_readiness(env)
    profile = profile_id or report.active_profile
    return CommandResult(
        payload={
            "profile": profile,
            "requires_confirmation": True,
            "modal": "auth_logout",
        },
        shape="markdown",
        text=(
            f"Auth logout confirmation requested for `{profile}`. "
            "The interactive TUI opens a confirmation modal for this action."
        ),
    )


def provider_login_capture_result(provider: str) -> CommandResult:
    """Return provider credential-capture guidance for interactive frontends."""
    return CommandResult(
        payload={
            "provider": provider,
            "modal": "provider_login",
            "requires_capture": True,
        },
        shape="markdown",
        text=(
            f"Provider auth capture requested for `{provider}`. "
            "The interactive TUI opens the credential capture modal."
        ),
    )


def operator_login_guidance_result() -> CommandResult:
    """Return operator-login guidance for inline shells."""
    return CommandResult(
        payload={
            "flow": "operator_login",
            "entrypoint": "craik login",
            "returns_to_shell": True,
        },
        shape="markdown",
        text=(
            "Operator login is handled by Craik's browser/device-code flow. "
            "Start it from an outer shell, then return here and use `/status`."
        ),
    )
