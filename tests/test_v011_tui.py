from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.contracts.models import AgentSessionState
from craik.runtime.paths import ensure_craik_home
from craik.runtime.shell.tui import (
    MultilineComposer,
    build_tui_snapshot,
    complete_tui_command,
    dispatch_tui_input,
    ratatui_command,
    ratatui_manifest_path,
    ratatui_runtime_diagnostics,
    render_approval_modal,
    render_tui_snapshot,
    run_ratatui_tui,
    run_textual_legacy_tui,
    run_tui,
)
from craik.runtime.store import LocalStore

runner = CliRunner()


def test_tui_starts_without_config_and_renders_nonblank(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    result = runner.invoke(app, ["tui"], env=env)
    root_result = runner.invoke(app, ["--tui"], env=env)

    assert result.exit_code == 0
    assert root_result.exit_code == 0
    assert "Craik TUI" in result.output
    assert "Provider/Auth Status" in result.output
    assert "State: unconfigured" in result.output
    assert "Redaction: on" in result.output
    assert "Craik TUI" in root_result.output


def test_tui_rs_command_launches_ratatui_runtime(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    class Process:
        def wait(self) -> int:
            return 0

    def fake_start_process(command, **kwargs):
        calls.append(command)
        assert kwargs["env"]["CRAIK_HOME"] == str(tmp_path / "home")
        return Process()

    monkeypatch.setattr(
        "craik.runtime.shell.ratatui.shutil.which",
        lambda name: f"/usr/bin/{name}" if name == "craik-tui-rs" else None,
    )
    monkeypatch.setattr(
        "craik.runtime.shell.tui.start_reviewed_local_process",
        fake_start_process,
    )

    exit_code = run_ratatui_tui(env={"CRAIK_HOME": str(tmp_path / "home")})
    result = runner.invoke(app, ["tui-rs"], env={"CRAIK_HOME": str(tmp_path / "home")})

    assert exit_code == 0
    assert result.exit_code == 0
    assert calls
    assert calls[0] == ["/usr/bin/craik-tui-rs"]


def test_tui_rs_command_falls_back_to_cargo_in_source_checkout(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    class Process:
        def wait(self) -> int:
            return 0

    def fake_start_process(command, **kwargs):
        calls.append(command)
        assert kwargs["env"]["CRAIK_HOME"] == str(tmp_path / "home")
        return Process()

    def fake_which(name: str) -> str | None:
        return "/usr/bin/cargo" if name == "cargo" else None

    monkeypatch.setattr("craik.runtime.shell.ratatui.shutil.which", fake_which)
    monkeypatch.setattr(
        "craik.runtime.shell.tui.start_reviewed_local_process",
        fake_start_process,
    )

    exit_code = run_ratatui_tui(env={"CRAIK_HOME": str(tmp_path / "home")})

    assert exit_code == 0
    assert calls[0][:4] == ["/usr/bin/cargo", "run", "--locked", "--manifest-path"]
    assert calls[0][4] == str(ratatui_manifest_path())


def test_tui_rs_command_reports_missing_cargo_for_source_fallback(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr("craik.runtime.shell.ratatui.shutil.which", lambda name: None)

    exit_code = run_ratatui_tui()

    assert exit_code == 2
    assert "Cargo was not found" in capsys.readouterr().err


def test_tui_rs_command_reports_missing_binary_and_checkout(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr("craik.runtime.shell.ratatui.shutil.which", lambda name: None)
    monkeypatch.setattr("craik.runtime.shell.ratatui.ratatui_manifest_path", lambda: None)

    exit_code = run_ratatui_tui()

    assert exit_code == 2
    assert "no source checkout fallback" in capsys.readouterr().err


def test_ratatui_runtime_diagnostics_explain_launch_paths(monkeypatch) -> None:
    manifest = Path("/repo/crates/craik-tui-rs/Cargo.toml")

    def fake_which(name: str) -> str | None:
        if name == "cargo":
            return "/usr/bin/cargo"
        return None

    monkeypatch.setattr("craik.runtime.shell.ratatui.shutil.which", fake_which)
    monkeypatch.setattr(
        "craik.runtime.shell.ratatui.ratatui_manifest_path",
        lambda: manifest,
    )

    diagnostics = ratatui_runtime_diagnostics()

    assert diagnostics.command == (
        "cargo",
        "run",
        "--locked",
        "--manifest-path",
        str(manifest),
    )
    assert diagnostics.cargo == "/usr/bin/cargo"
    assert diagnostics.installed_binary is None
    assert diagnostics.manifest == str(manifest)
    assert any("legacy_textual: craik tui-textual" in line for line in diagnostics.as_lines())


def test_ratatui_command_prefers_installed_binary(monkeypatch) -> None:
    monkeypatch.setattr(
        "craik.runtime.shell.ratatui.shutil.which",
        lambda name: f"/usr/local/bin/{name}" if name == "craik-tui-rs" else None,
    )

    assert ratatui_command() == ["/usr/local/bin/craik-tui-rs"]


def test_tui_runtime_env_can_select_rust(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    class Process:
        def wait(self) -> int:
            return 0

    def fake_start_process(command, **kwargs):
        calls.append(command)
        return Process()

    def fake_which(name: str) -> str | None:
        return "/usr/bin/cargo" if name == "cargo" else None

    monkeypatch.setattr("craik.runtime.shell.ratatui.shutil.which", fake_which)
    monkeypatch.setattr(
        "craik.runtime.shell.tui.start_reviewed_local_process",
        fake_start_process,
    )

    exit_code = run_tui(env={"CRAIK_HOME": str(tmp_path / "home"), "CRAIK_TUI_RUNTIME": "rust"})

    assert exit_code == 0
    assert calls[0][:2] == ["/usr/bin/cargo", "run"]


def test_tui_prefers_rust_for_interactive_terminal(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    class Process:
        def wait(self) -> int:
            return 0

    def fake_start_process(command, **kwargs):
        calls.append(command)
        return Process()

    def fake_which(name: str) -> str | None:
        return "/usr/bin/cargo" if name == "cargo" else None

    monkeypatch.setattr("craik.runtime.shell.ratatui.shutil.which", fake_which)
    monkeypatch.setattr(
        "craik.runtime.shell.tui.start_reviewed_local_process",
        fake_start_process,
    )

    exit_code = run_tui(env={"CRAIK_HOME": str(tmp_path / "home")}, stdin_isatty=True)

    assert exit_code == 0
    assert calls[0][:3] == ["/usr/bin/cargo", "run", "--locked"]


def test_tui_runtime_env_can_select_legacy_textual(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, str] | None] = []

    monkeypatch.setattr(
        "craik.runtime.shell.textual_app.terminal_supports_textual",
        lambda env=None: True,
    )
    monkeypatch.setattr(
        "craik.runtime.shell.textual_app.run_textual_tui",
        lambda *, env=None: calls.append(env) or 0,
    )

    exit_code = run_tui(
        env={
            "CRAIK_HOME": str(tmp_path / "home"),
            "CRAIK_TUI_RUNTIME": "textual",
        },
        stdin_isatty=True,
    )
    command_result = runner.invoke(
        app,
        ["tui-textual"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert exit_code == 0
    assert command_result.exit_code == 0
    assert calls


def test_legacy_textual_command_reports_unsupported_terminal(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "craik.runtime.shell.textual_app.terminal_supports_textual",
        lambda env=None: False,
    )

    assert run_textual_legacy_tui() == 2
    assert "Legacy Textual TUI is not supported" in capsys.readouterr().err


def test_tui_fixture_mode_status_and_store_panels(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home), "CRAIK_FIXTURE": "1"}
    paths = ensure_craik_home(env)
    store = LocalStore.from_paths(paths)
    now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
    try:
        store.initialize()
        store.put_agent_session_state(
            AgentSessionState(
                id="agent_session_tui",
                project_id="project_tui",
                operator_subject="operator:test",
                provider_id="fixture",
                model_id="fixture-model",
                mode="interactive",
                status="idle",
                started_at=now,
                last_activity_at=now,
                updated_at=now,
            )
        )
    finally:
        store.close()

    rendered = render_tui_snapshot(build_tui_snapshot(env))

    assert "State: fixture" in rendered
    assert "Sessions: 1" in rendered
    assert "Session Picker" in rendered
    assert "Gateway" in rendered


def test_tui_dispatches_shared_slash_commands(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    status = dispatch_tui_input("/status", env=env)
    model_help = dispatch_tui_input("/help model", env=env)

    assert json.loads(status.text)["state"] == "unconfigured"
    assert "Usage: /model" in model_help.text


def test_tui_autocomplete_and_multiline_composer() -> None:
    composer = MultilineComposer()

    assert complete_tui_command("/sta") == ["/status"]
    assert composer.accept("/compose") == (True, None)
    assert composer.accept("line one") == (True, None)
    assert composer.accept("line two") == (True, None)
    assert composer.accept(".") == (True, "line one\nline two")


def test_tui_approval_modal_redacts_secret_like_targets() -> None:
    rendered = render_approval_modal(
        approval_id="approval_docs",
        capability="model.chat",
        target="https://sk-live-secret-token@example.invalid",
        risk="provider call",
        policy="strict",
    )

    assert "Approval" in rendered
    assert "Retry: retry the blocked command after approval" in rendered
    assert "sk-live-secret-token" not in rendered
    assert "[REDACTED]" in rendered


def test_tui_scripted_input_renders_prompt_response_and_exits(tmp_path: Path) -> None:
    env = {"CRAIK_HOME": str(tmp_path / "home")}
    output: list[str] = []

    exit_code = run_tui(
        env=env,
        output_func=output.append,
        stdin_isatty=True,
        lines=["/help status", "hello", "/exit"],
    )

    assert exit_code == 0
    assert any("Craik TUI" in item for item in output)
    assert any("Usage: /status" in item for item in output)
    assert not any("Streaming output" in item for item in output)
    assert output[-1] == "Session ended."


def test_fallback_tui_prompt_ignores_quick_one_shot_flags(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    env = {"CRAIK_HOME": str(tmp_path / "home"), "CRAIK_QUICK": "1"}

    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)

    result = dispatch_tui_input("Upgrade Craik Docs", env=env)

    assert result.exit_code == 0, result.text
    assert result.command_name == "run"
    assert result.payload["schema"] == "craik.provider_backed_run_execution"
    assert "Audited run" in result.text
    assert "one-shot" not in result.text


def test_textual_tui_prompt_ignores_quick_one_shot_flags(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    env = {
        "CRAIK_HOME": str(tmp_path / "home"),
        "CRAIK_QUICK": "1",
        "CRAIK_TUI": "1",
    }

    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)

    result = dispatch_tui_input("Upgrade Craik Docs", env=env)

    assert result.exit_code == 0, result.text
    assert result.command_name == "run"
    assert result.payload["schema"] == "craik.provider_backed_run_execution"
    assert "Audited run" in result.text


def test_tui_prompt_defaults_to_audited_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    env = {"CRAIK_HOME": str(tmp_path / "home")}

    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)

    result = dispatch_tui_input("Upgrade Craik Docs", env=env)

    assert result.exit_code == 0, result.text
    assert result.command_name == "run"
    assert result.payload["schema"] == "craik.provider_backed_run_execution"
    assert "Audited run" in result.text
