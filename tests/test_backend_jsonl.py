from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.backend.jsonl import run_jsonl_gateway
from craik.runtime.reviewing.approvals import open_approval_request
from craik.runtime.store import LocalStore

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
    assert events[0]["data"]["protocol"] == "craik.tui.gateway"
    assert events[0]["data"]["protocol_version"] == "1"
    assert "approval.decide" in events[0]["data"]["capabilities"]
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


def test_jsonl_gateway_model_set_and_interrupt_events(tmp_path: Path) -> None:
    stdin = io.StringIO(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "model.set",
                        "model": "anthropic/claude-opus-4-7",
                        "display_name": "Anthropic Claude Opus 4.7 High",
                        "reasoning_effort": "high",
                        "options": {"thinking": True},
                    }
                ),
                json.dumps(
                    {
                        "type": "run.interrupt",
                        "run_id": "run_review_the_plan",
                        "reason": "operator requested stop",
                    }
                ),
                "",
            ]
        )
    )
    stdout = io.StringIO()

    run_jsonl_gateway(env=_env(tmp_path), stdin=stdin, stdout=stdout)
    events = _events(stdout.getvalue())

    assert [event["type"] for event in events] == [
        "session.ready",
        "model.changed",
        "run.interrupt.requested",
    ]
    model_payload = events[1]["data"]["payload"]
    active_profile_id = model_payload["active_profile_id"]
    assert model_payload["profiles"][active_profile_id]["display_name"] == (
        "Anthropic Claude Opus 4.7 High"
    )
    assert events[2]["run_id"] == "run_review_the_plan"


def test_jsonl_gateway_approval_decision_event(tmp_path: Path) -> None:
    env = _env(tmp_path)
    store = LocalStore.from_env(env)
    try:
        store.initialize()
        open_approval_request(
            store,
            approval_id="approval_jsonl",
            task_id="task_jsonl",
            capability="repo.write.docs",
            target="docs/",
            risk="docs write",
            policy="trusted-local",
            requested_by="test",
            retry_path="/run Retry",
        )
    finally:
        store.close()
    stdin = io.StringIO(
        json.dumps(
            {
                "type": "approval.decide",
                "approval_id": "approval_jsonl",
                "decision": "approved",
                "operator": "user:test",
                "reason": "fixture approval",
            }
        )
        + "\n"
    )
    stdout = io.StringIO()

    run_jsonl_gateway(env=env, stdin=stdin, stdout=stdout)
    events = _events(stdout.getvalue())

    assert [event["type"] for event in events] == ["session.ready", "approval.resolved"]
    assert events[1]["data"]["approval_id"] == "approval_jsonl"
    assert events[1]["data"]["payload"]["receipt"]["id"] == (
        "receipt_approval_approval_jsonl_approved"
    )


def test_jsonl_gateway_reports_slash_catalog(tmp_path: Path) -> None:
    stdin = io.StringIO('{"type":"slash.catalog"}\n{"type":"session.close"}\n')
    stdout = io.StringIO()

    run_jsonl_gateway(env=_env(tmp_path), stdin=stdin, stdout=stdout)
    events = _events(stdout.getvalue())

    assert [event["type"] for event in events] == ["session.ready", "slash.catalog"]
    names = {command["name"] for command in events[1]["data"]["commands"]}
    assert "run" in names
    assert "status" in names


def test_jsonl_gateway_reports_malformed_and_unsupported_messages(tmp_path: Path) -> None:
    stdin = io.StringIO(
        "\n".join(
            [
                "not-json",
                json.dumps({"type": "unknown.command"}),
                json.dumps({"type": "prompt.submit", "text": ""}),
                "",
            ]
        )
    )
    stdout = io.StringIO()

    run_jsonl_gateway(env=_env(tmp_path), stdin=stdin, stdout=stdout)
    events = _events(stdout.getvalue())

    assert events[0]["type"] == "session.ready"
    errors = [event["data"]["message"] for event in events[1:]]
    assert any("Expecting value" in message for message in errors)
    assert any("unsupported JSONL message type" in message for message in errors)
    assert any("prompt.submit requires non-empty text" in message for message in errors)
