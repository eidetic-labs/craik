from __future__ import annotations

from pathlib import Path

import typer

from craik.runtime.contract import CommandResult, craik_command
from craik.runtime.contract.auto_registry import AutoSlashRegistry
from craik.runtime.shell.model_settings import ModelSettings, ModelSettingsStore
from craik.runtime.shell.slash_completer import complete_slash_input


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik")}


def test_slash_completer_returns_command_candidates() -> None:
    values = [candidate.value for candidate in complete_slash_input("/au")]

    assert values == ["/auth"]


def test_slash_completer_uses_supplied_registry() -> None:
    app = typer.Typer()

    @app.command("alpha")
    @craik_command(payload_shape="kv")
    def alpha() -> CommandResult:
        return CommandResult(payload={"ok": True}, shape="kv")

    registry = AutoSlashRegistry.from_typer(app)

    values = [
        candidate.value
        for candidate in complete_slash_input("/al", registry=registry)
    ]

    assert values == ["/alpha"]


def test_slash_completer_returns_auth_login_providers() -> None:
    values = [candidate.value for candidate in complete_slash_input("/auth login ")]

    assert {"openai", "anthropic", "gemini", "local"}.issubset(set(values))


def test_slash_completer_returns_model_aliases_and_defaults(tmp_path: Path) -> None:
    env = _env(tmp_path)
    store = ModelSettingsStore.from_env(env)
    store.save(ModelSettings(aliases={"fast": "openai/gpt-4o-mini"}))

    values = [candidate.value for candidate in complete_slash_input("/model set ", env=env)]

    assert "fast" in values
    assert any(value.startswith("openai/") for value in values)
