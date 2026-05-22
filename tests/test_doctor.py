import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.auth import AuthProfile, AuthProfileStore, CredentialKind
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.doctor import run_doctor
from craik.runtime.gateway import default_gateway_config
from craik.runtime.paths import ensure_craik_home, resolve_craik_paths
from craik.runtime.store import LocalStore

runner = CliRunner()


def test_doctor_reports_missing_home_without_creating_it(tmp_path) -> None:
    home = tmp_path / "missing-home"

    payload = run_doctor(resolve_craik_paths({"CRAIK_HOME": str(home)}), env={})

    assert payload["status"] == "fail"
    checks = {item["name"]: item for item in payload["checks"]}
    assert checks["local_home"]["status"] == "fail"
    assert checks["local_store"]["status"] == "fail"
    assert checks["memory_backend"]["status"] == "warning"
    assert checks["auth_profiles"]["status"] == "pass"
    assert payload["auth_profiles"] == []
    assert not home.exists()


def test_doctor_reports_pass_with_setup_and_memory_config(tmp_path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        store.put_gateway_config(
            default_gateway_config(
                project_id="project_gateway",
                policy_envelope_id="policy_gateway",
            ).model_copy(update={"enabled": True})
        )
        payload = run_doctor(paths, env={"CRAIK_STIGMEM_URL": "http://127.0.0.1:18765"})
    finally:
        store.close()

    assert payload["status"] == "pass"
    checks = {item["name"]: item for item in payload["checks"]}
    assert checks["local_home"]["status"] == "pass"
    assert checks["local_store"]["status"] == "pass"
    assert checks["memory_backend"]["status"] == "pass"
    assert checks["gateway_config"]["status"] == "pass"
    assert checks["gateway_prerequisites"]["status"] == "pass"
    assert checks["policy"]["status"] == "pass"
    assert checks["auth_profiles"]["status"] == "pass"
    assert payload["auth_profiles"] == []


def test_doctor_reports_auth_profile_health(tmp_path, monkeypatch) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "craik-test-not-a-real-key")
    AuthProfileStore(paths.home).put(
        AuthProfile(
            id="anthropic:work",
            kind=CredentialKind.API_KEY,
            provider_family="anthropic",
            metadata={"env_var": "ANTHROPIC_API_KEY"},
            created_at=datetime(2026, 5, 17, tzinfo=UTC),
        )
    )

    payload = run_doctor(
        paths,
        env={
            "CRAIK_STIGMEM_URL": "http://127.0.0.1:18765",
            "ANTHROPIC_API_KEY": "craik-test-not-a-real-key",
        },
    )

    checks = {item["name"]: item for item in payload["checks"]}
    assert checks["auth_profiles"]["status"] == "pass"
    assert checks["auth_profile:anthropic:work"]["status"] == "pass"
    assert payload["auth_profiles"] == [
        {
            "id": "anthropic:work",
            "kind": "api-key",
            "provider_family": "anthropic",
            "last_used_at": None,
            "last_status": "unknown",
            "health": {"status": "ok", "detail": None, "expires_at": None},
        }
    ]


def test_doctor_warns_for_rejected_auth_profile(tmp_path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    AuthProfileStore(paths.home).put(
        AuthProfile(
            id="openai:missing",
            kind=CredentialKind.API_KEY,
            provider_family="openai",
            metadata={"env_var": "MISSING_OPENAI_KEY"},
            created_at=datetime(2026, 5, 17, tzinfo=UTC),
        )
    )

    payload = run_doctor(paths, env={})

    checks = {item["name"]: item for item in payload["checks"]}
    assert checks["auth_profiles"]["status"] == "warning"
    assert checks["auth_profile:openai:missing"]["status"] == "warning"
    assert payload["auth_profiles"][0]["health"]["status"] == "rejected"


def test_doctor_cli_outputs_json(tmp_path) -> None:
    home = tmp_path / "home"
    setup = runner.invoke(app, ["setup"], env={"CRAIK_HOME": str(home)})
    _put_operator_session(home)

    result = runner.invoke(app, ["doctor"], env={"CRAIK_HOME": str(home)})

    assert setup.exit_code == 0
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "warning"
    assert any(item["name"] == "memory_backend" for item in payload["checks"])
    assert "auth_profiles" in payload


def test_doctor_cli_requires_operator_session_before_state_read(tmp_path) -> None:
    home = tmp_path / "home"
    setup = runner.invoke(app, ["setup"], env={"CRAIK_HOME": str(home)})

    result = runner.invoke(app, ["doctor"], env={"CRAIK_HOME": str(home)})

    assert setup.exit_code == 0
    assert result.exit_code != 0
    assert "active operator session required; run craik auth login" in result.output


def _put_operator_session(home: Path) -> None:
    ensure_craik_home({"CRAIK_HOME": str(home)})
    OperatorSessionStore(home).put(
        OperatorSession(
            subject="operator-123",
            email="operator@example.test",
            groups=["platform"],
            issuer="https://issuer.example.test",
            id_token_jti="session-token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
