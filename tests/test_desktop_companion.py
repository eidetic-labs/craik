import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.companions.desktop_companion import (
    DesktopCompanionConfig,
    DesktopCompanionSurface,
    desktop_approval_notification,
    desktop_companion_action,
    desktop_companion_actions,
    desktop_companion_decision,
    desktop_companion_snapshot,
)
from craik.runtime.gateway import default_gateway_config, gateway_running_state
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore

runner = CliRunner()


def test_desktop_companion_allows_supported_documented_surface() -> None:
    decision = desktop_companion_decision(
        DesktopCompanionSurface(
            id="desktop_status_panel",
            support_level="supported",
            docs_ref="docs/reference/desktop-companion.md",
        )
    )

    assert decision.allowed is True
    assert decision.status == "allowed"
    assert decision.reason == (
        "desktop companion surface preserves consent, storage, notification, policy, "
        "evidence, and receipt controls"
    )
    assert decision.required_controls == [
        "operator_consent",
        "encrypted_local_storage",
        "notification_controls",
        "background_action_controls",
        "policy_context",
        "evidence_links",
        "receipts",
        "documented_decision",
    ]


def test_desktop_companion_requires_review_for_experimental_surface() -> None:
    decision = desktop_companion_decision(
        DesktopCompanionSurface(
            id="desktop_live_actions",
            support_level="experimental",
            docs_ref="docs/reference/desktop-companion.md",
        )
    )

    assert decision.allowed is False
    assert decision.status == "review_required"
    assert decision.reason == "experimental desktop companion surfaces require explicit review"


def test_desktop_companion_defers_deferred_surface() -> None:
    decision = desktop_companion_decision(
        DesktopCompanionSurface(
            id="desktop_always_on_agent",
            support_level="deferred",
            docs_ref="docs/reference/desktop-companion.md",
        )
    )

    assert decision.allowed is False
    assert decision.status == "deferred"
    assert decision.reason == "desktop companion surface is deferred by product posture"


def test_desktop_companion_blocks_secret_storage() -> None:
    decision = desktop_companion_decision(
        DesktopCompanionSurface(
            id="desktop_secret_cache",
            support_level="supported",
            stores_secrets=True,
        )
    )

    assert decision.allowed is False
    assert decision.status == "blocked"
    assert decision.reason == "desktop companion surfaces must not store secrets"


def test_desktop_companion_blocks_missing_required_controls() -> None:
    cases = [
        (
            DesktopCompanionSurface(
                id="desktop_no_consent",
                support_level="supported",
                operator_consent_required=False,
            ),
            "desktop companion surfaces require operator consent",
        ),
        (
            DesktopCompanionSurface(
                id="desktop_plain_storage",
                support_level="supported",
                local_storage_encrypted=False,
            ),
            "desktop companion local storage must be encrypted",
        ),
        (
            DesktopCompanionSurface(
                id="desktop_no_notifications",
                support_level="supported",
                notification_controls=False,
            ),
            "desktop companion notifications require operator controls",
        ),
        (
            DesktopCompanionSurface(
                id="desktop_no_background_controls",
                support_level="supported",
                background_action_controls=False,
            ),
            "desktop companion background actions require controls",
        ),
        (
            DesktopCompanionSurface(
                id="desktop_no_policy",
                support_level="supported",
                preserves_policy_context=False,
            ),
            "desktop companion surfaces must preserve policy and evidence links",
        ),
        (
            DesktopCompanionSurface(
                id="desktop_no_receipts",
                support_level="supported",
                requires_receipts=False,
            ),
            "desktop companion surfaces require receipts",
        ),
    ]

    for surface, reason in cases:
        decision = desktop_companion_decision(surface)

        assert decision.allowed is False
        assert decision.status == "blocked"
        assert decision.reason == reason


def test_desktop_companion_snapshot_reports_local_dashboard_and_gateway(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    paths = ensure_craik_home(env)
    store = LocalStore.from_paths(paths)
    now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    try:
        store.initialize()
        config = default_gateway_config(created_at=now)
        store.put_gateway_config(config)
        store.put_gateway_runtime_state(gateway_running_state(config, pid=1234, started_at=now))
    finally:
        store.close()

    snapshot = desktop_companion_snapshot(env=env)

    assert snapshot.status == "allowed"
    assert snapshot.local_dashboard_url == "http://127.0.0.1:8787/"
    assert snapshot.gateway_status == "running"
    assert snapshot.provider_auth_status == "unconfigured"
    assert snapshot.local_vs_remote == "local-only"
    assert any(action.id == "open_dashboard" for action in snapshot.actions)


def test_desktop_companion_warns_on_remote_dashboard_target(tmp_path: Path) -> None:
    snapshot = desktop_companion_snapshot(
        env={"CRAIK_HOME": str(tmp_path / "home")},
        config=DesktopCompanionConfig(dashboard_host="192.0.2.10"),
    )

    assert snapshot.local_vs_remote == "review"
    assert "not local-only" in snapshot.warnings[0]


def test_desktop_companion_actions_are_deterministic() -> None:
    actions = desktop_companion_actions()
    gateway_restart = desktop_companion_action("gateway_restart")

    assert [action.id for action in actions] == [
        "open_dashboard",
        "gateway_status",
        "gateway_start",
        "gateway_stop",
        "gateway_restart",
        "doctor",
        "update_check",
    ]
    assert gateway_restart.requires_confirmation is True
    assert gateway_restart.command == "craik gateway restart"


def test_desktop_approval_notification_redacts_target() -> None:
    notification = desktop_approval_notification(
        "approval_docs",
        capability="model.chat",
        target="https://sk-live-secret-token@example.invalid",
    )

    assert notification.deep_link.endswith("/approvals?approval=approval_docs")
    assert "sk-live-secret-token" not in notification.body
    assert "[REDACTED]" in notification.body


def test_desktop_cli_surfaces_status_menu_actions_and_notifications(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    status = runner.invoke(app, ["desktop", "status"], env=env)
    menu = runner.invoke(app, ["desktop", "menu"], env=env)
    action = runner.invoke(app, ["desktop", "action", "doctor"], env=env)
    notification = runner.invoke(
        app,
        [
            "desktop",
            "notify-approval",
            "approval_docs",
            "model.chat",
            "token=secret-value",
        ],
        env=env,
    )
    update = runner.invoke(app, ["desktop", "update-check"], env=env)

    assert status.exit_code == 0
    assert json.loads(status.stdout)["surface_id"] == "desktop_companion_mvp"
    assert menu.exit_code == 0
    assert any(item["id"] == "gateway_status" for item in json.loads(menu.stdout))
    assert json.loads(action.stdout)["command"] == "craik doctor"
    assert notification.exit_code == 0
    assert "secret-value" not in notification.stdout
    assert update.exit_code == 0
    assert json.loads(update.stdout)["installed_version"]
