from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.backend.session import (
    active_provider_and_model,
    execute_prompt,
    live_provider_enabled,
)
from craik.runtime.modeling import ModelSettingsStore
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.store import LocalStore

runner = CliRunner()


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik")}


def _repo(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    return repo


def test_gateway_prompt_execution_emits_audited_events(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = {**_env(tmp_path), "CRAIK_FIXTURE": "1"}

    result = execute_prompt("Upgrade Craik Docs", env=env, source="tui")
    payload = result.payload_with_events()

    assert payload["task"]["id"] == "task_upgrade_craik_docs"
    assert payload["run"]["task_id"] == "task_upgrade_craik_docs"
    event_types = [event.type for event in result.events]
    assert event_types[0] == "prompt.submitted"
    assert "model.selected" in event_types
    assert "receipt.created" in event_types
    assert event_types[-1] == "run.completed"
    assert payload["gateway_events"][-1]["type"] == "run.completed"
    store = LocalStore.from_env(env)
    try:
        outputs = store.list_run_outputs()
    finally:
        store.close()
    gateway_output = next(
        output for output in outputs if output.step_result_id == "gateway_event_history"
    )
    assert gateway_output.run_id == payload["run"]["id"]
    assert gateway_output.summary == (
        f"Gateway recorded {len(payload['gateway_events'])} event(s) for audited prompt run."
    )
    assert gateway_output.observed_output["event_count"] == len(payload["gateway_events"])
    assert gateway_output.observed_output["events"][-1]["type"] == "run.completed"


def test_slash_run_uses_gateway_prompt_events(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)

    result = dispatch_slash_command("/run Upgrade Craik Docs", env=env)

    assert result.exit_code == 0, result.text
    assert isinstance(result.payload, dict)
    assert [event["type"] for event in result.payload["gateway_events"]][-1] == "run.completed"


def test_cli_run_prompt_mirrors_slash_gateway_path(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = _env(tmp_path)

    result = runner.invoke(app, ["run", "prompt", "Upgrade Craik Docs"], env=env)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["task"]["id"] == "task_upgrade_craik_docs"
    assert payload["gateway_events"][-1]["type"] == "run.completed"


def test_gateway_model_selection_supports_local_provider_aliases(tmp_path: Path) -> None:
    env = _env(tmp_path)

    dispatch_slash_command("/model set ollama/llama3.2", env=env)
    settings = ModelSettingsStore.from_env(env).load()

    assert active_provider_and_model(env) == ("provider_local_ollama", "llama3.2")
    assert settings.active_profile is not None
    assert settings.active_profile.provider_id == "provider_local_ollama"
    assert settings.active_profile.display_name == "Ollama llama3.2"
    assert live_provider_enabled(env) is True
    assert live_provider_enabled({**env, "CRAIK_FIXTURE": "1"}) is False


def test_gateway_payload_includes_active_model_profile(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    env = {**_env(tmp_path), "CRAIK_FIXTURE": "1"}
    dispatch_slash_command(
        "/model set anthropic/claude-opus-4-7",
        env=env,
    )

    result = execute_prompt("Upgrade Craik Docs", env=env, source="tui")
    payload = result.payload_with_events()

    assert payload["model_profile"]["provider_id"] == "provider_anthropic"
    model_event = next(
        event for event in payload["gateway_events"] if event["type"] == "model.selected"
    )
    assert model_event["data"]["profile"]["display_name"] == "Anthropic Claude claude-opus-4-7"


def test_cli_model_set_persists_provider_profile_options(tmp_path: Path) -> None:
    env = _env(tmp_path)

    result = runner.invoke(
        app,
        [
            "model",
            "set",
            "anthropic/claude-opus-4-7",
            "--display-name",
            "Anthropic Claude Opus 4.7 High",
            "--reasoning-effort",
            "high",
            "--service-tier",
            "priority",
            "--temperature",
            "0.2",
            "--max-output-tokens",
            "8192",
            "--option",
            "thinking=true",
        ],
        env=env,
    )

    assert result.exit_code == 0, result.output
    settings = ModelSettingsStore.from_env(env).load()
    assert settings.active_profile is not None
    assert settings.active_profile.display_name == "Anthropic Claude Opus 4.7 High"
    assert settings.active_profile.provider_id == "provider_anthropic"
    assert settings.active_profile.options == {
        "max_output_tokens": 8192,
        "reasoning_effort": "high",
        "service_tier": "priority",
        "temperature": 0.2,
        "thinking": True,
    }
