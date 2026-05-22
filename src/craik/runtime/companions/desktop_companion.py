"""Desktop companion app posture decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from craik.contracts.models import CraikModel
from craik.runtime.dashboard import DashboardConfig, dashboard_url
from craik.runtime.paths import resolve_craik_paths
from craik.runtime.policy.redaction import redact
from craik.runtime.policy.text import sanitize_runtime_text
from craik.runtime.projects.update_guidance import update_guidance_payload
from craik.runtime.shell.readiness import resolve_readiness
from craik.runtime.store import DATABASE_NAME, LocalStore

DesktopCompanionSupportLevel = Literal["supported", "experimental", "deferred"]
DesktopCompanionStatus = Literal["allowed", "review_required", "deferred", "blocked"]
DesktopCompanionActionKind = Literal["dashboard", "gateway", "doctor", "update", "approval"]


class DesktopCompanionSurface(CraikModel):
    """Candidate desktop companion surface."""

    id: str
    support_level: DesktopCompanionSupportLevel
    operator_consent_required: bool = True
    preserves_policy_context: bool = True
    preserves_evidence_links: bool = True
    requires_receipts: bool = True
    local_storage_encrypted: bool = True
    stores_secrets: bool = False
    notification_controls: bool = True
    background_action_controls: bool = True
    docs_ref: str | None = None


class DesktopCompanionDecision(CraikModel):
    """Decision describing whether a desktop companion surface can be used."""

    status: DesktopCompanionStatus
    allowed: bool
    reason: str
    surface_id: str
    required_controls: list[str] = Field(default_factory=list)


class DesktopCompanionAction(CraikModel):
    """Menu-bar action exposed by the desktop companion MVP."""

    id: str
    label: str
    kind: DesktopCompanionActionKind
    command: str
    local_only: bool = True
    requires_confirmation: bool = False


class DesktopApprovalNotification(CraikModel):
    """Approval notification metadata with a local dashboard deep link."""

    approval_id: str
    title: str
    body: str
    deep_link: str
    redacted: bool = True


class DesktopCompanionSnapshot(CraikModel):
    """Desktop companion MVP status payload."""

    surface_id: str
    status: DesktopCompanionStatus
    local_dashboard_url: str
    gateway_status: str
    provider_auth_status: str
    local_vs_remote: str
    actions: list[DesktopCompanionAction]
    approval_notifications: list[DesktopApprovalNotification] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    redacted: bool = True


@dataclass(frozen=True)
class DesktopCompanionConfig:
    """Runtime options for desktop companion status rendering."""

    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8787


def desktop_companion_decision(surface: DesktopCompanionSurface) -> DesktopCompanionDecision:
    """Evaluate desktop companion app posture."""
    if surface.stores_secrets:
        return _blocked(surface, "desktop companion surfaces must not store secrets")
    if not surface.operator_consent_required:
        return _blocked(surface, "desktop companion surfaces require operator consent")
    if not surface.local_storage_encrypted:
        return _blocked(surface, "desktop companion local storage must be encrypted")
    if not surface.notification_controls:
        return _blocked(surface, "desktop companion notifications require operator controls")
    if not surface.background_action_controls:
        return _blocked(surface, "desktop companion background actions require controls")
    if not surface.preserves_policy_context or not surface.preserves_evidence_links:
        return _blocked(
            surface,
            "desktop companion surfaces must preserve policy and evidence links",
        )
    if not surface.requires_receipts:
        return _blocked(surface, "desktop companion surfaces require receipts")
    if surface.support_level == "deferred":
        return DesktopCompanionDecision(
            status="deferred",
            allowed=False,
            reason="desktop companion surface is deferred by product posture",
            surface_id=surface.id,
            required_controls=_controls(surface),
        )
    if surface.support_level == "experimental":
        return DesktopCompanionDecision(
            status="review_required",
            allowed=False,
            reason="experimental desktop companion surfaces require explicit review",
            surface_id=surface.id,
            required_controls=_controls(surface),
        )
    return DesktopCompanionDecision(
        status="allowed",
        allowed=True,
        reason=(
            "desktop companion surface preserves consent, storage, notification, policy, "
            "evidence, and receipt controls"
        ),
        surface_id=surface.id,
        required_controls=_controls(surface),
    )


def default_desktop_companion_surface() -> DesktopCompanionSurface:
    """Return the supported desktop companion MVP surface."""
    return DesktopCompanionSurface(
        id="desktop_companion_mvp",
        support_level="supported",
        docs_ref="docs/reference/desktop-companion.md",
    )


def desktop_companion_snapshot(
    *,
    env: dict[str, str] | None = None,
    config: DesktopCompanionConfig | None = None,
) -> DesktopCompanionSnapshot:
    """Build a redacted desktop companion status/menu snapshot."""
    active_config = config or DesktopCompanionConfig()
    surface = default_desktop_companion_surface()
    decision = desktop_companion_decision(surface)
    readiness = resolve_readiness(env)
    gateway_status = _gateway_status(env)
    dashboard = dashboard_url(
        DashboardConfig(host=active_config.dashboard_host, port=active_config.dashboard_port)
    )
    warnings = list(readiness.warnings)
    if not decision.allowed:
        warnings.append(decision.reason)
    if active_config.dashboard_host not in {"127.0.0.1", "localhost", "::1"}:
        warnings.append("desktop companion dashboard target is not local-only")
    return DesktopCompanionSnapshot(
        surface_id=surface.id,
        status=decision.status,
        local_dashboard_url=_safe(dashboard),
        gateway_status=_safe(gateway_status),
        provider_auth_status=_safe(readiness.state),
        local_vs_remote="local-only" if not warnings else "review",
        actions=desktop_companion_actions(),
        approval_notifications=[],
        warnings=[_safe(warning) for warning in warnings],
        redacted=True,
    )


def desktop_companion_actions() -> list[DesktopCompanionAction]:
    """Return deterministic desktop menu/tray actions."""
    return [
        DesktopCompanionAction(
            id="open_dashboard",
            label="Open Dashboard",
            kind="dashboard",
            command="craik dashboard",
        ),
        DesktopCompanionAction(
            id="gateway_status",
            label="Gateway Status",
            kind="gateway",
            command="craik gateway status",
        ),
        DesktopCompanionAction(
            id="gateway_start",
            label="Start Gateway",
            kind="gateway",
            command="craik gateway start",
            requires_confirmation=True,
        ),
        DesktopCompanionAction(
            id="gateway_stop",
            label="Stop Gateway",
            kind="gateway",
            command="craik gateway stop",
            requires_confirmation=True,
        ),
        DesktopCompanionAction(
            id="gateway_restart",
            label="Restart Gateway",
            kind="gateway",
            command="craik gateway restart",
            requires_confirmation=True,
        ),
        DesktopCompanionAction(
            id="doctor",
            label="Run Doctor",
            kind="doctor",
            command="craik doctor",
        ),
        DesktopCompanionAction(
            id="update_check",
            label="Check For Updates",
            kind="update",
            command="craik update --check",
        ),
    ]


def desktop_companion_action(action_id: str) -> DesktopCompanionAction:
    """Return one desktop companion action by id."""
    for action in desktop_companion_actions():
        if action.id == action_id:
            return action
    raise KeyError(action_id)


def desktop_approval_notification(
    approval_id: str,
    *,
    capability: str,
    target: str,
    dashboard_base_url: str = "http://127.0.0.1:8787",
) -> DesktopApprovalNotification:
    """Create a redacted approval notification with dashboard deep link."""
    safe_id = _safe(approval_id)
    return DesktopApprovalNotification(
        approval_id=safe_id,
        title="Craik approval required",
        body=f"{_safe(capability)} requires review for {_safe(target)}",
        deep_link=f"{dashboard_base_url.rstrip('/')}/approvals?approval={safe_id}",
    )


def desktop_update_check_payload(installed_version: str) -> dict[str, object]:
    """Return the companion update-check payload."""
    return update_guidance_payload(installed_version=installed_version)


def _blocked(surface: DesktopCompanionSurface, reason: str) -> DesktopCompanionDecision:
    return DesktopCompanionDecision(
        status="blocked",
        allowed=False,
        reason=reason,
        surface_id=surface.id,
        required_controls=_controls(surface),
    )


def _controls(surface: DesktopCompanionSurface) -> list[str]:
    controls = ["operator_consent", "encrypted_local_storage", "notification_controls"]
    if surface.background_action_controls:
        controls.append("background_action_controls")
    if surface.preserves_policy_context:
        controls.append("policy_context")
    if surface.preserves_evidence_links:
        controls.append("evidence_links")
    if surface.requires_receipts:
        controls.append("receipts")
    if surface.docs_ref:
        controls.append("documented_decision")
    return controls


def _gateway_status(env: dict[str, str] | None) -> str:
    paths = resolve_craik_paths(env)
    if not (paths.state / DATABASE_NAME).exists():
        return "not configured"
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        states = store.list_gateway_runtime_states()
    finally:
        store.close()
    if not states:
        return "not configured"
    latest = sorted(states, key=lambda state: state.updated_at)[-1]
    return str(latest.status)


def _safe(value: str) -> str:
    return sanitize_runtime_text(str(redact(value).value))
