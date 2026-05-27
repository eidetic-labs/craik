from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.backend.jsonl import run_jsonl_gateway

runner = CliRunner()


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik")}


def _repo(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)


def _events(output: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.splitlines() if line.strip()]


def test_jsonl_gateway_reports_ready_and_status(tmp_path: Path) -> None:
    stdin = io.StringIO('{"type":"session.status"}\n{"type":"session.close"}\n')
    stdout = io.StringIO()

    exit_code = run_jsonl_gateway(env=_env(tmp_path), stdin=stdin, stdout=stdout)
    events = _events(stdout.getvalue())

    assert exit_code == 0
    assert events[0]["type"] == "session.ready"
    assert events[1]["type"] == "session.status"
    assert events[1]["data"]["state"] == "unconfigured"


def test_jsonl_gateway_executes_prompt_with_run_events(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path, monkeypatch)
    stdin = io.StringIO('{"type":"prompt.submit","text":"Upgrade Craik Docs"}\n')
    stdout = io.StringIO()

    run_jsonl_gateway(env=_env(tmp_path), stdin=stdin, stdout=stdout)
    event_types = [event["type"] for event in _events(stdout.getvalue())]

    assert event_types[0] == "session.ready"
    assert "prompt.submitted" in event_types
    assert "receipt.created" in event_types
    assert event_types[-1] == "run.completed"


def test_tui_backend_jsonl_cli_status(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["tui-backend", "--jsonl"],
        input='{"type":"session.status"}\n{"type":"session.close"}\n',
        env=_env(tmp_path),
    )

    assert result.exit_code == 0
    events = _events(result.stdout)
    assert [event["type"] for event in events] == ["session.ready", "session.status"]
