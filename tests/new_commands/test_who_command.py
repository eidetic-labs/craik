"""Coverage for the v0.12.8 /who command."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from craik.cli import app
from craik.runtime.auth import AuthProfile, AuthProfileStore, CredentialKind
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.contract import CommandResult
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.providers.provider_transport import ProviderFamily
from craik.runtime.shell.commands import who_result
from craik.runtime.shell.slash_commands import dispatch_slash_command

SNAPSHOT_ROOT = Path(__file__).resolve().parents[1] / "snapshots" / "slash"


def test_who_slash_command_renders_unauthenticated_snapshot(tmp_path: Path) -> None:
    result = dispatch_slash_command("/who", env={"CRAIK_HOME": str(tmp_path)})

    snapshot = SNAPSHOT_ROOT / "who" / "width-80.txt"

    assert result.exit_code == 0
    assert result.payload["status"] == "unauthenticated"
    assert result.text + "\n" == snapshot.read_text(encoding="utf-8")


def test_who_result_reports_active_operator_visible_scope(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path)}
    OperatorSessionStore.from_env(env).put(
        OperatorSession(
            subject="operator:alpha",
            email="alpha@example.test",
            display_name="Alpha Operator",
            groups=["prod-deploy"],
            issuer="https://issuer.example.test",
            id_token_jti="jti-alpha",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    store = AuthProfileStore.from_env(env)
    store.put(_profile("openai:default"))
    store.put(_profile("anthropic:group", groups=["prod-deploy"]))
    store.put(_profile("gemini:other", operators=["operator:beta"]))

    result = who_result(env)

    assert isinstance(result, CommandResult)
    assert result.shape == "kv"
    assert result.payload["status"] == "authenticated"
    assert result.payload["operator"]["subject"] == "operator:alpha"
    assert result.payload["auth_scope"]["visible_profiles"] == 2
    assert result.payload["auth_scope"]["total_profiles"] == 3
    assert result.payload["auth_scope"]["scoped_profiles"] == 2
    assert result.payload["auth_scope"]["visible_profile_ids"] == [
        "anthropic:group",
        "openai:default",
    ]
    assert "Alpha Operator (operator:alpha)" in (result.text or "")


def test_who_command_is_registered_as_derived_slash_command() -> None:
    registry = AutoSlashRegistry.from_typer(app)

    assert registry.spec_by_name("/who") is not None


def _profile(
    profile_id: str,
    *,
    operators: list[str] | None = None,
    groups: list[str] | None = None,
) -> AuthProfile:
    family = profile_id.split(":", 1)[0]
    return AuthProfile(
        id=profile_id,
        kind=CredentialKind.API_KEY,
        provider_family=cast(ProviderFamily, family),
        metadata={"env_var": "PROVIDER_API_KEY"},
        created_at=datetime.now(UTC),
        authorized_operators=operators,
        authorized_operator_groups=groups,
    )
