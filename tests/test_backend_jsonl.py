from __future__ import annotations

import io
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.contracts.models import CapabilityReceipt, ReceiptResult
from craik.runtime.backend import jsonl as jsonl_backend
from craik.runtime.backend.event_contract import (
    gateway_event_contract,
    known_event_types,
    validate_gateway_event,
    validate_gateway_events,
)
from craik.runtime.backend.events import BackendEvent
from craik.runtime.backend.jsonl import run_jsonl_gateway
from craik.runtime.paths import ensure_craik_home
from craik.runtime.reviewing.approvals import open_approval_request
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.store import LocalStore

runner = CliRunner()

CONTRACT_DOCS_PATH = Path("docs/reference/tui-gateway-events.md")
GATEWAY_FIXTURE_DIR = Path("tests/fixtures/gateway")


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


def _contract_event_types() -> dict[str, object]:
    event_types = gateway_event_contract()["event_types"]
    assert isinstance(event_types, dict)
    return event_types


def _contract_required_fields(rule: object) -> str:
    assert isinstance(rule, dict)
    requirements = rule["requirements"]
    assert isinstance(requirements, list)
    rendered: list[str] = []
    for requirement in requirements:
        assert isinstance(requirement, dict)
        kind = requirement["kind"]
        if kind == "non_empty_string":
            path = str(requirement["path"]).removeprefix("data.")
            rendered.append(f"{path} string")
        elif kind == "array":
            path = str(requirement["path"]).removeprefix("data.")
            rendered.append(f"{path} array")
        elif kind in {"one_non_empty_string", "one_present"}:
            paths = [str(path).removeprefix("data.") for path in requirement["paths"]]
            if len(paths) == 2:
                rendered.append(f"one of {paths[0]} or {paths[1]}")
            else:
                rendered.append(f"one of {', '.join(paths[:-1])}, or {paths[-1]}")
        else:
            raise AssertionError(f"unsupported contract requirement kind: {kind}")

    return "; ".join(rendered)


def _documented_required_fields() -> dict[str, str]:
    docs = CONTRACT_DOCS_PATH.read_text(encoding="utf-8")
    table_pattern = re.compile(r"^\| `(?P<event>[^`]+)` \| (?P<fields>.+) \|$", re.MULTILINE)
    return {
        match.group("event"): match.group("fields").replace("`", "")
        for match in table_pattern.finditer(docs)
    }


def test_gateway_event_contract_validates_fixture_corpus() -> None:
    fixture_paths = sorted(GATEWAY_FIXTURE_DIR.glob("*.jsonl"))

    assert fixture_paths
    for fixture_path in fixture_paths:
        events = _events(fixture_path.read_text(encoding="utf-8"))

        assert validate_gateway_events(events) == [], fixture_path


def test_gateway_event_contract_docs_table_matches_contract() -> None:
    expected = {
        event_type: _contract_required_fields(rule)
        for event_type, rule in _contract_event_types().items()
    }

    assert _documented_required_fields() == expected


def test_gateway_event_fixture_corpus_covers_contract_event_types() -> None:
    observed: set[str] = set()
    for fixture_path in sorted(GATEWAY_FIXTURE_DIR.glob("*.jsonl")):
        observed.update(
            str(event["type"]) for event in _events(fixture_path.read_text(encoding="utf-8"))
        )

    assert observed == set(_contract_event_types())


def test_gateway_event_contract_is_single_source_for_known_events() -> None:
    contract = gateway_event_contract()
    event_types = contract["event_types"]

    assert set(event_types) == known_event_types()
    assert event_types["run.completed"]["requirements"] == [
        {"kind": "non_empty_string", "path": "run_id", "message": "run_id is required"},
        {
            "kind": "non_empty_string",
            "path": "data.status",
            "message": "data.status must be a non-empty string",
        },
    ]


def test_gateway_event_contract_reports_required_fields() -> None:
    issues = validate_gateway_event(
        {
            "type": "run.completed",
            "run_id": None,
            "task_id": None,
            "data": {"status": "completed"},
        }
    )

    assert len(issues) == 1
    assert issues[0].event_type == "run.completed"
    assert issues[0].message == "run_id is required"


def test_jsonl_gateway_reports_ready_and_status(tmp_path: Path) -> None:
    env = _env(tmp_path)
    dispatch_slash_command(
        "/model set anthropic/claude-opus-4-7 --reasoning-effort high",
        env=env,
    )
    dispatch_slash_command("/mode auto", env=env)
    stdin = io.StringIO('{"type":"session.status"}\n{"type":"session.close"}\n')
    stdout = io.StringIO()

    exit_code = run_jsonl_gateway(env=env, stdin=stdin, stdout=stdout)
    events = _events(stdout.getvalue())

    assert exit_code == 0
    assert events[0]["type"] == "session.ready"
    assert events[0]["data"]["protocol"] == "craik.tui.gateway"
    assert events[0]["data"]["protocol_version"] == "1"
    assert "approval.decide" in events[0]["data"]["capabilities"]
    assert events[1]["type"] == "session.status"
    assert events[1]["data"]["state"] == "unconfigured"
    assert events[1]["data"]["claude_permission_mode"] == "auto"
    assert events[1]["data"]["model"] == "anthropic/claude-opus-4-7"
    assert events[1]["data"]["provider_id"] == "provider_anthropic"
    assert events[1]["data"]["provider_family"] == "anthropic"
    assert events[1]["data"]["reasoning_effort"] == "high"


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
    assert events[1]["data"]["provider_id"] == "provider_anthropic"
    assert events[1]["data"]["provider_family"] == "anthropic"
    assert events[1]["data"]["reasoning_effort"] == "high"
    assert model_payload["profiles"][active_profile_id]["display_name"] == (
        "Anthropic Claude Opus 4.7 High"
    )
    assert events[2]["run_id"] == "run_review_the_plan"


def test_jsonl_gateway_slash_model_and_mode_emit_state_events(tmp_path: Path) -> None:
    stdin = io.StringIO(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "slash.submit",
                        "text": "/model set anthropic/claude-opus-4-7 --reasoning-effort high",
                    }
                ),
                json.dumps({"type": "slash.submit", "text": "/mode auto"}),
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
        "slash.completed",
        "session.status",
        "slash.completed",
    ]
    assert events[1]["data"]["model"] == "anthropic/claude-opus-4-7"
    assert events[1]["data"]["reasoning_effort"] == "high"
    assert events[3]["data"]["claude_permission_mode"] == "auto"


def test_jsonl_gateway_slash_effort_emits_model_state_event(tmp_path: Path) -> None:
    env = _env(tmp_path)
    dispatch_slash_command("/model set anthropic/claude-opus-4-7", env=env)
    stdin = io.StringIO(
        "\n".join(
            [
                json.dumps({"type": "slash.submit", "text": "/effort high"}),
                "",
            ]
        )
    )
    stdout = io.StringIO()

    run_jsonl_gateway(env=env, stdin=stdin, stdout=stdout)
    events = _events(stdout.getvalue())

    assert [event["type"] for event in events] == [
        "session.ready",
        "model.changed",
        "slash.completed",
    ]
    assert events[1]["data"]["model"] == "anthropic/claude-opus-4-7"
    assert events[1]["data"]["reasoning_effort"] == "high"


def test_jsonl_gateway_slash_effort_default_emits_explicit_default(tmp_path: Path) -> None:
    env = _env(tmp_path)
    dispatch_slash_command(
        "/model set anthropic/claude-opus-4-7 --reasoning-effort high", env=env
    )
    stdin = io.StringIO(
        "\n".join(
            [
                json.dumps({"type": "slash.submit", "text": "/effort default"}),
                "",
            ]
        )
    )
    stdout = io.StringIO()

    run_jsonl_gateway(env=env, stdin=stdin, stdout=stdout)
    events = _events(stdout.getvalue())

    assert [event["type"] for event in events] == [
        "session.ready",
        "model.changed",
        "slash.completed",
    ]
    assert events[1]["data"]["model"] == "anthropic/claude-opus-4-7"
    assert events[1]["data"]["reasoning_effort"] == "default"


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
    commands = {command["name"]: command for command in events[1]["data"]["commands"]}
    names = set(commands)
    assert "run" in names
    assert "status" in names
    assert commands["effort"]["choices"] == {"effort": ["default", "low", "medium", "high", "max"]}
    assert commands["mode"]["choices"] == {
        "mode": [
            "ask",
            "auto",
            "acceptEdits",
            "plan",
            "dontAsk",
            "bypassPermissions",
        ]
    }
    assert commands["mode"]["current_value"] == "ask"
    assert commands["theme"]["choices"] == {"theme": ["dark", "light", "monochrome"]}
    assert commands["theme"]["current_value"] == "dark"
    assert commands["theme"]["mutating"] is True
    assert commands["theme"]["cli_mirror"] == "theme"
    assert commands["clear"]["requires_confirmation"] is True
    assert commands["clear"]["confirm_message"].startswith("This discards")
    assert "set" in commands["model"]["subcommands"]
    assert "anthropic/claude-sonnet-4-20250514" in commands["model"]["model_choices"]
    assert "openai/gpt-5.2" in commands["model"]["model_choices"]
    assert commands["model"]["examples"] == [
        "/model set openai/gpt-4o-mini --reasoning-effort high"
    ]


def test_jsonl_gateway_reports_persisted_session_history(tmp_path: Path) -> None:
    env = _env(tmp_path)
    store = LocalStore.from_paths(ensure_craik_home(env))
    try:
        store.initialize()
        store.put_receipt(_receipt("receipt_history_1", task_id="task_history_1"))
    finally:
        store.close()
    stdin = io.StringIO('{"type":"session.history"}\n{"type":"session.close"}\n')
    stdout = io.StringIO()

    run_jsonl_gateway(env=env, stdin=stdin, stdout=stdout)
    events = _events(stdout.getvalue())

    assert [event["type"] for event in events] == ["session.ready", "session.history"]
    assert events[1]["data"]["receipts"] == [
        {
            "id": "receipt_history_1",
            "task_id": "task_history_1",
            "actor": "agent:test",
            "capability": "shell.test",
            "target": "pytest",
            "policy": "strict",
            "reason": "Validate session history.",
            "status": "passed",
            "summary": "History receipt.",
            "created_at": "2026-05-26T12:00:00+00:00",
            "auth_profile_id": None,
            "operator_subject": None,
            "tools": ["Bash"],
            "files": ["tests/test_backend_jsonl.py"],
            "commands": ["uv run pytest tests/test_backend_jsonl.py"],
            "approvals": ["approval_history_1"],
            "outputs": ["History receipt."],
            "evidence_ids": ["evidence_history_1"],
            "handoff_ids": ["handoff_history_1"],
        }
    ]


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


def test_jsonl_gateway_rejects_invalid_backend_events(tmp_path: Path, monkeypatch) -> None:
    def _execute_prompt(*args: object, stream, **kwargs: object) -> None:
        stream(BackendEvent(type="run.completed", data={"status": "completed"}))

    monkeypatch.setattr(jsonl_backend, "execute_prompt", _execute_prompt)
    stdin = io.StringIO('{"type":"prompt.submit","text":"Review contract"}\n')
    stdout = io.StringIO()

    run_jsonl_gateway(env=_env(tmp_path), stdin=stdin, stdout=stdout)
    events = _events(stdout.getvalue())

    assert [event["type"] for event in events] == ["session.ready", "error"]
    assert "Gateway backend emitted invalid event" in events[1]["data"]["message"]
    assert "event 0 `run.completed`: run_id is required" in events[1]["data"]["message"]
    assert events[1]["data"]["kind"] == "contract_violation"
    assert events[1]["data"]["event_type"] == "run.completed"
    assert events[1]["data"]["issues"] == ["run_id is required"]
    assert "required fields before retrying" in events[1]["data"]["recovery"]


def _receipt(receipt_id: str, *, task_id: str) -> CapabilityReceipt:
    return CapabilityReceipt(
        id=receipt_id,
        task_id=task_id,
        actor="agent:test",
        capability="shell.test",
        target="pytest",
        policy_profile="strict",
        reason="Validate session history.",
        result=ReceiptResult(
            status="passed",
            summary="History receipt.",
            metadata={
                "tools": ["Bash"],
                "files": ["tests/test_backend_jsonl.py"],
                "commands": ["uv run pytest tests/test_backend_jsonl.py"],
                "approvals": ["approval_history_1"],
                "outputs": ["History receipt."],
                "evidence_ids": ["evidence_history_1"],
                "handoff_ids": ["handoff_history_1"],
            },
        ),
        redacted=True,
        created_at=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )
