from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from typer.testing import CliRunner

from craik.cli import app
from craik.contracts.models import AgentSessionState
from craik.runtime.auth import AuthProfile, AuthProfileStore, CredentialKind, CredentialStatus
from craik.runtime.auth import health_check as auth_health_check
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.auth.redaction import masked_metadata
from craik.runtime.paths import ensure_craik_home
from craik.runtime.providers.provider_transport import ProviderFamily
from craik.runtime.shell.agent_shell import run_shell
from craik.runtime.shell.readiness import resolve_readiness
from craik.runtime.shell.slash_commands import dispatch_slash_command, list_slash_commands
from craik.runtime.store import LocalStore

runner = CliRunner()


def test_default_craik_launches_shell_status_before_auth(tmp_path: Path) -> None:
    result = runner.invoke(app, [], env={"CRAIK_HOME": str(tmp_path / "home")})

    assert result.exit_code == 0
    assert "Craik Agent Shell" in result.output
    assert "State: unconfigured" in result.output
    assert "run craik auth login <provider>" in result.output


def test_one_shot_is_quiet_and_reports_missing_readiness(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["-z", "Summarize readiness", "--allow-argv-prompt"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    assert "WARNING: prompt was supplied via argv" in result.output
    assert "Craik is not ready" in result.output
    assert "Craik Agent Shell" not in result.output


def test_one_shot_rejects_argv_prompt_without_acknowledgment(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["-z", "Summarize readiness"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 2
    assert "argv-supplied prompts are visible" in result.output
    assert "Craik is not fully ready" not in result.stdout


def test_one_shot_reads_prompt_from_stdin_without_warning(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["-z", "-"],
        input="Summarize readiness\n",
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    assert result.output.startswith("Craik is not ready")
    assert "argv-supplied prompts" not in result.output
    assert "WARNING: prompt was supplied via argv" not in result.output


def test_plain_shell_prompt_defaults_to_audited_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    env = {"CRAIK_HOME": str(tmp_path / "home")}
    output: list[str] = []

    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)

    exit_code = run_shell(
        env=env,
        stdin_isatty=True,
        lines=["Upgrade Craik Docs", "/exit"],
        output_func=output.append,
    )

    assert exit_code == 0
    assert any("Audited run" in item for item in output)
    assert not any("one-shot model execution" in item for item in output)


def test_chat_prompt_uses_same_argv_safety_gate(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    rejected = runner.invoke(app, ["chat", "-q", "hello"], env=env)
    accepted = runner.invoke(
        app,
        ["chat", "-q", "-", "--allow-argv-prompt"],
        input="hello\n",
        env=env,
    )

    assert rejected.exit_code == 2
    assert "argv-supplied prompts are visible" in rejected.output
    assert accepted.exit_code == 0
    assert "WARNING: prompt was supplied via argv" not in accepted.output


def test_status_command_and_slash_status_share_readiness(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    cli_status = runner.invoke(app, ["status"], env=env)
    slash_status = runner.invoke(app, ["slash", "/status"], env=env)

    assert cli_status.exit_code == 0
    assert slash_status.exit_code == 0
    assert json.loads(cli_status.stdout)["state"] == json.loads(slash_status.stdout)["state"]


def test_readiness_transitions_from_operator_only_to_fully_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home), "CRAIK_CREDENTIAL_BACKEND": "file"}
    _put_operator_session(home)
    _allow_health_check(monkeypatch)

    assert resolve_readiness(env).state == "operator-only"

    login = runner.invoke(
        app,
        ["auth", "login", "openai", "--env-var", "OPENAI_API_KEY", "--dry-run"],
        env=env,
    )
    assert login.exit_code == 0
    assert json.loads(login.stdout)["dry_run"] is True

    login_write = runner.invoke(
        app,
        ["auth", "login", "openai", "--no-browser"],
        input="openai-test-key\n",
        env=env,
    )
    model_set = runner.invoke(app, ["model", "set", "openai/gpt-5"], env=env)

    assert login_write.exit_code == 0
    assert model_set.exit_code == 0
    assert resolve_readiness(env).state == "fully-ready"


def test_single_operator_mode_provider_and_model_are_ready(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {
        "CRAIK_HOME": str(home),
        "CRAIK_LIVE": "0",
        "OPENAI_API_KEY": "openai-key",
    }
    AuthProfileStore.from_env(env).put(_auth_profile("openai:default"))
    model_set = runner.invoke(app, ["model", "set", "openai/gpt-5"], env=env)
    chat = runner.invoke(app, ["chat", "-q", "-"], input="hello\n", env=env)

    report = resolve_readiness(env)

    assert model_set.exit_code == 0
    assert report.operator_required is False
    assert report.operator_authenticated is False
    assert report.state == "fully-ready"
    assert chat.exit_code == 0
    assert "openai fixture completed plan with status completed." in chat.output
    assert "not ready" not in chat.output


def test_anthropic_one_shot_routes_claude_cli_profile_through_gateway(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    env = {
        "CRAIK_HOME": str(home),
        "ANTHROPIC_API_KEY": "should-not-reach-claude-cli",
        "CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat01-from-claude-code",
    }
    AuthProfileStore.from_env(env).put(
        AuthProfile(
            id="anthropic:default",
            kind=CredentialKind.MARKER,
            provider_family="anthropic",
            metadata={"external_runtime": "claude-cli", "credential_mode": "claude-cli"},
            created_at=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
            last_status="ok",
        )
    )
    runner.invoke(app, ["model", "set", "anthropic/claude-sonnet-4-20250514"], env=env)
    monkeypatch.setattr(
        "craik.runtime.auth.login.claude_cli_runtime_status",
        lambda: CredentialStatus(status="ok"),
    )

    seen: dict[str, object] = {}

    def _execute(prompt: str, **kwargs) -> dict[str, object]:
        seen["prompt"] = prompt
        seen["env"] = kwargs["env"]
        return _gateway_payload("from cli")

    monkeypatch.setattr("craik.runtime.backend.session._execute_claude_code_prompt", _execute)

    chat = runner.invoke(app, ["chat", "-q", "-"], input="hello\n", env=env)

    assert chat.exit_code == 0
    assert "from cli" in chat.output
    assert "Audited run `run_chat` completed" in chat.output
    assert "Receipts: receipt_chat" in chat.output
    assert seen["prompt"] == "hello"


def test_anthropic_one_shot_preserves_claude_permission_mode_for_gateway(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    env = {
        "CRAIK_HOME": str(home),
        "CRAIK_CLAUDE_PERMISSION_MODE": "plan",
    }
    AuthProfileStore.from_env(env).put(
        AuthProfile(
            id="anthropic:default",
            kind=CredentialKind.MARKER,
            provider_family="anthropic",
            metadata={"external_runtime": "claude-cli", "credential_mode": "claude-cli"},
            created_at=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
            last_status="ok",
        )
    )
    runner.invoke(app, ["model", "set", "anthropic/claude-opus-4-7"], env=env)
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        "craik.runtime.auth.login.claude_cli_runtime_status",
        lambda: CredentialStatus(status="ok"),
    )

    def _execute(prompt: str, **kwargs) -> dict[str, object]:
        seen["prompt"] = prompt
        seen["env"] = kwargs["env"]
        return _gateway_payload("from cli")

    monkeypatch.setattr("craik.runtime.backend.session._execute_claude_code_prompt", _execute)

    chat = runner.invoke(app, ["chat", "-q", "-"], input="hello\n", env=env)

    assert chat.exit_code == 0
    assert seen["prompt"] == "hello"
    assert seen["env"]["CRAIK_CLAUDE_PERMISSION_MODE"] == "plan"


def test_anthropic_one_shot_without_final_text_still_reports_audit_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    AuthProfileStore.from_env(env).put(
        AuthProfile(
            id="anthropic:default",
            kind=CredentialKind.MARKER,
            provider_family="anthropic",
            metadata={"external_runtime": "claude-cli", "credential_mode": "claude-cli"},
            created_at=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
            last_status="ok",
        )
    )
    runner.invoke(app, ["model", "set", "anthropic/claude-sonnet-4-20250514"], env=env)
    monkeypatch.setattr(
        "craik.runtime.auth.login.claude_cli_runtime_status",
        lambda: CredentialStatus(status="ok"),
    )

    def _execute(prompt: str, **kwargs) -> dict[str, object]:
        return _gateway_payload("")

    monkeypatch.setattr("craik.runtime.backend.session._execute_claude_code_prompt", _execute)

    chat = runner.invoke(
        app,
        ["chat", "-q", "-"],
        input="Can you review the implementation plan on the desktop for the next phase?\n",
        env=env,
    )

    assert chat.exit_code == 0
    assert "Audited run `run_chat` completed" in chat.output
    assert "Handoff: `handoff_chat`" in chat.output
    assert "Receipts: receipt_chat" in chat.output
    assert "completed without output" not in chat.output


def test_audited_mode_requires_operator_session(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {
        "CRAIK_HOME": str(home),
        "CRAIK_OPERATOR_REQUIRED": "1",
        "OPENAI_API_KEY": "openai-key",
    }
    AuthProfileStore.from_env(env).put(_auth_profile("openai:default"))
    model_set = runner.invoke(app, ["model", "set", "openai/gpt-5"], env=env)
    chat = runner.invoke(app, ["chat", "-q", "-"], input="hello\n", env=env)

    report = resolve_readiness(env)

    assert model_set.exit_code == 0
    assert report.operator_required is True
    assert report.state == "provider-only"
    assert "operator session" in report.missing
    assert report.next_actions[0] == "run craik login"
    assert chat.exit_code == 0
    assert "State: provider-only" in chat.output
    assert "run craik login" in chat.output


def test_readiness_filters_profiles_by_active_operator(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {
        "CRAIK_HOME": str(home),
        "OPENAI_API_KEY": "openai-key",
        "ANTHROPIC_API_KEY": "anthropic-key",
    }
    _put_operator_session(home, subject="operator:a", groups=["team-a"])
    profile_store = AuthProfileStore.from_env(env)
    profile_store.put(_auth_profile("openai:operator-a", authorized_operators=["operator:a"]))
    profile_store.put(_auth_profile("openai:operator-b", authorized_operators=["operator:b"]))
    profile_store.put(_auth_profile("anthropic:legacy"))

    model_set = runner.invoke(app, ["model", "set", "openai/gpt-5"], env=env)
    report = resolve_readiness(env)
    model_list = runner.invoke(app, ["model", "list"], env=env)
    auth_list = runner.invoke(app, ["auth", "list"], env=env)
    auth_status = runner.invoke(app, ["auth", "status"], env=env)
    configured_ids = {
        profile["id"] for profile in json.loads(model_list.stdout)["configured_profiles"]
    }
    auth_list_ids = {profile["id"] for profile in json.loads(auth_list.stdout)}
    auth_status_ids = {profile["id"] for profile in json.loads(auth_status.stdout)}

    assert model_set.exit_code == 0
    assert report.state == "fully-ready"
    assert model_list.exit_code == 0
    assert configured_ids == {"anthropic:legacy", "openai:operator-a"}
    assert auth_list.exit_code == 0
    assert auth_status.exit_code == 0
    assert auth_list_ids == configured_ids
    assert auth_status_ids == configured_ids


def test_slash_help_and_unknown_suggestion(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    assert any(command.name == "provider" for command in list_slash_commands())
    help_result = dispatch_slash_command("/help provider", env=env)
    unknown_result = dispatch_slash_command("/stats", env=env)

    assert "Usage: /provider" in help_result.text
    assert "unknown slash command" in unknown_result.text
    assert "/status" in unknown_result.text


def test_model_profile_session_and_usage_commands(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    _put_operator_session(home)
    paths = ensure_craik_home(env)
    store = LocalStore.from_paths(paths)
    now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    try:
        store.initialize()
        store.put_agent_session_state(
            AgentSessionState(
                id="agent_session_docs",
                project_id="project_docs",
                operator_subject="operator:test",
                provider_id="openai",
                model_id="gpt-5",
                mode="interactive",
                status="idle",
                started_at=now,
                last_activity_at=now,
                updated_at=now,
            )
        )
    finally:
        store.close()

    assert runner.invoke(app, ["model", "set", "openai/gpt-5"], env=env).exit_code == 0
    model_status = runner.invoke(app, ["model", "status"], env=env)
    profile_create = runner.invoke(
        app,
        ["profile", "create", "release", "--description", "Release work"],
        env=env,
    )
    profile_use = runner.invoke(app, ["profile", "use", "release"], env=env)
    sessions = runner.invoke(app, ["session", "list"], env=env)
    session_export = runner.invoke(app, ["session", "export", "agent_session_docs"], env=env)
    usage = runner.invoke(app, ["usage"], env=env)

    assert json.loads(model_status.stdout)["active_model"] == "openai/gpt-5"
    assert profile_create.exit_code == 0
    assert profile_use.exit_code == 0
    assert profile_create.exception is None
    assert usage.exception is None
    assert json.loads(sessions.stdout)[0]["id"] == "agent_session_docs"
    assert json.loads(session_export.stdout)["redacted"] is True
    assert json.loads(usage.stdout)["token_usage"] == "unknown"


def test_auth_storage_status_is_redacted(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["auth", "storage", "status"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert set(payload) == {"backend", "secure", "status", "warning"}


def test_auth_metadata_unknown_keys_default_to_masked() -> None:
    result = masked_metadata(
        {
            "env_var": "CRAIK_OPENAI_API_KEY",
            "surprise_field": "should-not-leak",
        }
    )

    assert result["env_var"] == "CRAIK_OPENAI_API_KEY"
    assert result["surprise_field"] == "***"


def _put_operator_session(
    home: Path,
    *,
    subject: str = "operator:test",
    groups: list[str] | None = None,
) -> None:
    ensure_craik_home({"CRAIK_HOME": str(home)})
    OperatorSessionStore(home).put(
        OperatorSession(
            subject=subject,
            email="operator@example.test",
            groups=groups or ["platform"],
            issuer="https://issuer.example.test",
            id_token_jti="session-token",
            expires_at=datetime(2026, 5, 22, 13, 0, tzinfo=UTC),
        )
    )


class _FakeHealthResponse:
    def __enter__(self) -> _FakeHealthResponse:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def getcode(self) -> int:
        return 200


def _allow_health_check(monkeypatch) -> None:
    def _urlopen(request, *, timeout: float) -> _FakeHealthResponse:
        return _FakeHealthResponse()

    monkeypatch.setattr(auth_health_check, "_health_check_urlopen", _urlopen)


def _gateway_payload(text: str) -> dict[str, object]:
    return {
        "schema": "craik.claude_code_run_execution",
        "status": "completed",
        "task": {"id": "task_chat"},
        "run": {"id": "run_chat", "task_id": "task_chat", "status": "completed"},
        "handoff": {"id": "handoff_chat"},
        "receipt_ids": ["receipt_chat"],
        "run_outputs": [
            {
                "observed_output": {"text": text},
                "diagnostics": [],
            }
        ],
    }


def _auth_profile(
    profile_id: str,
    *,
    authorized_operators: list[str] | None = None,
    authorized_operator_groups: list[str] | None = None,
) -> AuthProfile:
    family = profile_id.split(":", 1)[0]
    return AuthProfile(
        id=profile_id,
        kind=CredentialKind.API_KEY,
        provider_family=cast(ProviderFamily, family),
        metadata={"env_var": f"{family.upper()}_API_KEY"},
        created_at=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
        authorized_operators=authorized_operators,
        authorized_operator_groups=authorized_operator_groups,
    )
