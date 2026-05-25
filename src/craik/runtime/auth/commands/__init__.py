"""CommandResult helpers for auth CLI and TUI projections."""

from craik.runtime.auth.commands.command import (
    auth_logout_confirmation_result,
    auth_status_result,
    auth_summary_result,
    operator_login_guidance_result,
    provider_login_capture_result,
)

__all__ = [
    "auth_logout_confirmation_result",
    "auth_status_result",
    "auth_summary_result",
    "operator_login_guidance_result",
    "provider_login_capture_result",
]
