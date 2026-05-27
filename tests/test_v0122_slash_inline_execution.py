from __future__ import annotations

import json
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from craik.runtime.auth.profile import AuthProfile, CredentialKind
from craik.runtime.auth.sources.anthropic_claude_cli import store_claude_cli_token_profile
from craik.runtime.auth.store import AuthProfileStore
from craik.runtime.shell.contract_runtime.builtin_slash_commands import (
    CLAUDE_CODE_RUN_APPROVED_ENV,
    _active_provider_and_model,
    _live_provider_enabled,
    claude_code_progress,
)
from craik.runtime.shell.credential_storage import CredentialStorageStatus
from craik.runtime.shell.slash_commands import dispatch_slash_command
from craik.runtime.store import LocalStore


def _env(tmp_path: Path) -> dict[str, str]:
    return {"CRAIK_HOME": str(tmp_path / ".craik")}


@pytest.mark.parametrize(
    "command",
    [
        "/auth",
        "/auth login openai",
        "/auth logout default",
        "/provider",
        "/provider login openai",
        "/model",
        "/model list",
        "/mode",
        "/copy",
        "/export",
        "/sessions",
        "/approvals",
        "/approvals decide approval_1",
        "/handoffs",
        "/receipts",
        "/skills",
        "/memory",
        "/gateway",
        "/doctor",
        "/run",
        "/run list",
    ],
)
def test_slash_commands_do_not_route_back_to_cli(tmp_path: Path, command: str) -> None:
    result = dispatch_slash_command(command, env=_env(tmp_path))

    assert "Use `craik " not in result.text
    assert "run `craik " not in result.text


def test_model_set_persists_active_model(tmp_path: Path) -> None:
    env = _env(tmp_path)

    result = dispatch_slash_command("/model set openai/gpt-4o-mini", env=env)
    status = dispatch_slash_command("/model", env=env)

    assert result.text == "Active model set to `openai/gpt-4o-mini`."
    assert json.loads(status.text)["active_model"] == "openai/gpt-4o-mini"


def test_audited_provider_run_uses_active_live_model(tmp_path: Path) -> None:
    env = _env(tmp_path)

    dispatch_slash_command("/model set anthropic/claude-opus-4-7", env=env)

    assert _active_provider_and_model(env) == ("provider_anthropic", "claude-opus-4-7")
    assert _live_provider_enabled(env) is True
    assert _live_provider_enabled({**env, "CRAIK_FIXTURE": "1"}) is False


def test_audited_anthropic_marker_routes_to_claude_code_stream_without_preapproval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    env = _env(tmp_path)
    AuthProfileStore.from_env(env).put(_claude_cli_marker_profile())
    dispatch_slash_command("/model set anthropic/claude-sonnet-4-20250514", env=env)
    original_popen = subprocess.Popen

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.shutil.which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    class _Process:
        stdout = iter(
            [
                (
                    '{"type":"assistant","message":{"content":[{"type":"tool_use",'
                    '"name":"Read","input":{"file_path":"README.md"}}]}}\n'
                ),
                '{"type":"result","result":"from stream"}\n',
            ]
        )

        pid = 12345

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    def _popen(args, **kwargs):
        if args[0] != "claude":
            return original_popen(args, **kwargs)
        assert "--output-format" in args
        assert "stream-json" in args
        return _Process()

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.subprocess.Popen",
        _popen,
    )

    result = dispatch_slash_command("/run Upgrade Craik Docs", env=env)

    assert result.exit_code == 0, result.text
    assert "Audited run" in result.text
    assert "from stream" in result.text
    assert isinstance(result.payload, dict)
    event_types = [event["type"] for event in result.payload["gateway_events"]]
    assert "run.started" in event_types
    assert "run.progress" in event_types
    assert event_types[-1] == "run.completed"
    assert "unsupported auth profile kind/source" not in result.text
    assert "requires operator approval" not in result.text
    store = LocalStore.from_env(env)
    try:
        output = store.get_run_output("runout_upgrade_craik_docs_claude_code")
        receipt = store.get_receipt("receipt_run_upgrade_craik_docs_claude_code")
        authority_receipt = store.get_receipt("receipt_upgrade_craik_docs_claude_code_approval")
        handoff = store.get_handoff("handoff_upgrade_craik_docs")
    finally:
        store.close()
    assert output is not None
    assert receipt is not None
    assert authority_receipt is not None
    assert handoff is not None
    assert output.observed_output["raw_stream_events"]
    assert output.observed_output["structured_events"]
    assert output.observed_output["activity"]["tools"] == ["Read"]
    assert output.observed_output["activity"]["files"] == ["README.md"]
    assert authority_receipt.result.metadata["default_attested_backend"] is True


def test_mode_set_persists_claude_permission_mode(tmp_path: Path) -> None:
    env = _env(tmp_path)

    result = dispatch_slash_command("/mode acceptEdits", env=env)
    status = dispatch_slash_command("/mode", env=env)

    assert result.text == "Claude permission mode: `acceptEdits`."
    assert json.loads(status.text)["claude_permission_mode"] == "acceptEdits"
    assert env["CRAIK_CLAUDE_PERMISSION_MODE"] == "acceptEdits"


def test_resume_persists_active_session_without_argument_loss(tmp_path: Path) -> None:
    env = _env(tmp_path)

    result = dispatch_slash_command("/resume session_alpha", env=env)
    sessions = dispatch_slash_command("/sessions", env=env)

    assert result.text == "Active session set to `session_alpha`."
    assert json.loads(sessions.text)["active_session"] == "session_alpha"


def test_run_prompt_creates_task_case_and_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    env = _env(tmp_path)

    result = dispatch_slash_command("/run Upgrade Craik Docs", env=env)
    runs = dispatch_slash_command("/run list", env=env)

    assert result.exit_code == 0, result.text
    assert "Audited run" in result.text
    assert "task_upgrade_craik_docs" in result.text
    assert "task_upgrade_craik_docs" in runs.text


def test_run_prompt_allows_unbalanced_quotes_in_prompt_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    env = _env(tmp_path)

    result = dispatch_slash_command('/run Update docs with "quoted examples', env=env)

    assert result.exit_code == 0, result.text
    assert "Audited run" in result.text
    store = LocalStore.from_env(env)
    try:
        task = store.get_task("task_update_docs_with_quoted_examples")
    finally:
        store.close()
    assert task is not None
    assert task.objective == 'Update docs with "quoted examples'


def test_run_claude_code_backend_creates_audited_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    env = {
        **_env(tmp_path),
        "CRAIK_CLAUDE_PERMISSION_MODE": "plan",
        CLAUDE_CODE_RUN_APPROVED_ENV: "1",
    }
    dispatch_slash_command("/model set anthropic/claude-opus-4-7", env=env)
    calls: list[list[str]] = []
    original_popen = subprocess.Popen

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.shutil.which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    class _Process:
        def __init__(self, args, **kwargs):
            assert kwargs["env"]["CRAIK_CLAUDE_PERMISSION_MODE"] == "plan"
            assert "ANTHROPIC_API_KEY" not in kwargs["env"]
            assert "CLAUDE_CODE_OAUTH_TOKEN" not in kwargs["env"]
            prompt = args[args.index("-p") + 1]
            assert "Claude Code Execution" in prompt
            assert "Execute the task using the available Claude Code tools" in prompt
            self.stdout = iter(
                [
                    (
                        '{"type":"assistant","message":{"content":[{"type":"tool_use",'
                        '"name":"Read","input":{"file_path":"docs/index.md"}}]}}\n'
                    ),
                    (
                        '{"type":"assistant","message":{"content":[{"type":"tool_use",'
                        '"name":"Bash","input":{"command":"uv run pytest -q"}}]}}\n'
                    ),
                    (
                        '{"type":"assistant","message":{"content":[{"type":"tool_use",'
                        '"name":"Edit","input":{"file_path":"docs/index.md",'
                        '"old_string":"old docs","new_string":"new docs"}}]}}\n'
                    ),
                    (
                        '{"type":"assistant","message":{"content":[{"type":"tool_result",'
                        '"content":"diff --git a/docs/index.md b/docs/index.md\\n'
                        '+new docs\\n-old docs"}]}}\n'
                    ),
                    (
                        '{"type":"result","subtype":"success","result":"docs updated",'
                        '"permission_denials":[{"tool_name":"Edit",'
                        '"reason":"repo.write.docs declined"}]}\n'
                    ),
                ]
            )

        def wait(self, timeout=None):
            return 0

    def _popen(args, **kwargs):
        if args[0] != "claude":
            return original_popen(args, **kwargs)
        calls.append(list(args))
        return _Process(args, **kwargs)

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.subprocess.Popen",
        _popen,
    )

    result = dispatch_slash_command(
        "/run --backend claude-code Upgrade Craik Docs",
        env={
            **env,
            "ANTHROPIC_API_KEY": "should-not-reach-claude",
            "CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat01-from-claude-code",
        },
    )
    runs = dispatch_slash_command("/run list", env=env)
    inspected = dispatch_slash_command("/run inspect task_upgrade_craik_docs", env=env)
    timeline = dispatch_slash_command("/run timeline task_upgrade_craik_docs", env=env)

    assert result.exit_code == 0, result.text
    assert "Claude Code run" in result.text
    assert "Activity:" in result.text
    assert "- Tools: `Read`, `Bash`, `Edit`" in result.text
    assert "- Files: `docs/index.md`" in result.text
    assert "- Commands:\n  - `uv run pytest -q`" in result.text
    assert "Final output:\ndocs updated" in result.text
    assert "Next:\n- `/run inspect run_upgrade_craik_docs`" in result.text
    assert "receipt_run_upgrade_craik_docs_claude_code" in result.text
    assert "task_upgrade_craik_docs" in runs.text
    assert "claude" in inspected.text
    assert "Claude Code is using `Read`" in timeline.text
    store = LocalStore.from_env(env)
    try:
        output = store.get_run_output("runout_upgrade_craik_docs_claude_code")
        handoff = store.get_handoff("handoff_upgrade_craik_docs")
        attestations = store.list_tool_result_attestations()
        grants = {grant.capability for grant in store.list_capability_grants()}
    finally:
        store.close()
    assert output is not None
    assert "raw_stream_events" in output.observed_output
    assert "progress_events" in output.observed_output
    assert any(
        str(event).startswith("Claude Code diff:")
        for event in output.observed_output["progress_events"]
    )
    assert "receipt_upgrade_craik_docs_claude_code_approval" in output.receipt_ids
    activity = output.observed_output["activity"]
    assert activity["files"] == ["docs/index.md"]
    assert activity["commands"] == ["uv run pytest -q"]
    assert activity["tools"] == ["Read", "Bash", "Edit"]
    assert activity["permission_denials"][0]["tool"] == "Edit"
    assert handoff is not None
    assert handoff.files_changed == ["docs/index.md"]
    assert "uv run pytest -q" in handoff.commands_run
    assert {attestation.tool_name for attestation in attestations} >= {
        "claude_code.Read",
        "claude_code.Bash",
        "claude_code.Edit",
    }
    assert all(
        attestation.receipt_id == "receipt_run_upgrade_craik_docs_claude_code"
        for attestation in attestations
    )
    assert output.observed_output["structured_events"]
    assert "repo.read" in grants
    assert "repo.write.docs" in grants
    assert "receipt.write" in grants
    assert calls
    assert calls[0][0:6] == [
        "claude",
        "--tools",
        "default",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    assert "--tools" in calls[0]
    assert calls[0][calls[0].index("--tools") + 1] == "default"
    assert "--output-format" in calls[0]
    assert calls[0][calls[0].index("--output-format") + 1] == "stream-json"
    assert "--verbose" in calls[0]
    assert "--model" in calls[0]
    assert calls[0][calls[0].index("--model") + 1] == "opus"
    assert "--permission-mode" in calls[0]
    assert calls[0][calls[0].index("--permission-mode") + 1] == "plan"
    assert "-p" in calls[0]


def test_run_claude_code_backend_invokes_claude_without_auth_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    env = {**_env(tmp_path), CLAUDE_CODE_RUN_APPROVED_ENV: "1"}
    calls: list[list[str]] = []
    original_popen = subprocess.Popen

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.shutil.which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    class _Process:
        stdout = iter(['{"type":"result","result":"docs updated"}\n'])

        def wait(self, timeout=None):
            return 0

    def _popen(args, **kwargs):
        if args[0] != "claude":
            return original_popen(args, **kwargs)
        calls.append(list(args))
        assert args[0:3] == ["claude", "--tools", "default"]
        assert "-p" in args
        return _Process()

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.subprocess.Popen",
        _popen,
    )

    result = dispatch_slash_command("/run --backend claude-code Upgrade Craik Docs", env=env)
    runs = dispatch_slash_command("/run list", env=env)

    assert result.exit_code == 0
    assert "Claude Code run" in result.text
    assert "task_upgrade_craik_docs" in runs.text
    assert calls
    assert ["claude", "auth", "status"] not in calls


def test_run_claude_code_backend_uses_cli_auth_without_stored_bearer_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    env = {**_env(tmp_path), CLAUDE_CODE_RUN_APPROVED_ENV: "1"}
    original_popen = subprocess.Popen

    monkeypatch.setattr(
        "craik.runtime.auth.sources.anthropic_claude_cli.put_cached_credential",
        lambda ref, value, *, env=None: CredentialStorageStatus(
            backend="test-keyring",
            status="available",
            secure=True,
        ),
    )
    profile = store_claude_cli_token_profile("sk-ant-oat01-from-keyring", env=env).profile
    AuthProfileStore.from_env(env).put(profile)
    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.shutil.which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    class _Process:
        stdout = iter(['{"type":"result","result":"docs updated"}\n'])

        def wait(self, timeout=None):
            return 0

    def _popen(args, **kwargs):
        if args[0] != "claude":
            return original_popen(args, **kwargs)
        assert "ANTHROPIC_API_KEY" not in kwargs["env"]
        assert "CLAUDE_CODE_OAUTH_TOKEN" not in kwargs["env"]
        return _Process()

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.subprocess.Popen",
        _popen,
    )

    result = dispatch_slash_command("/run --backend=claude-code Upgrade Craik Docs", env=env)

    assert result.exit_code == 0, result.text
    assert "Claude Code run" in result.text


def test_run_claude_code_backend_summarizes_activity_when_result_body_is_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    env = {**_env(tmp_path), CLAUDE_CODE_RUN_APPROVED_ENV: "1"}
    original_popen = subprocess.Popen

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.shutil.which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    class _Process:
        stdout = iter(
            [
                (
                    '{"type":"assistant","message":{"content":[{"type":"tool_use",'
                    '"name":"Read","input":{"file_path":"docs/index.md"}}]}}\n'
                ),
                '{"type":"result","subtype":"success"}\n',
            ]
        )

        def wait(self, timeout=None):
            return 0

    def _popen(args, **kwargs):
        if args[0] != "claude":
            return original_popen(args, **kwargs)
        return _Process()

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.subprocess.Popen",
        _popen,
    )

    result = dispatch_slash_command("/run --backend=claude-code Upgrade Craik Docs", env=env)

    store = LocalStore.from_env(env)
    try:
        output = store.get_run_output("runout_upgrade_craik_docs_claude_code")
    finally:
        store.close()

    assert result.exit_code == 0
    assert output is not None
    text = output.observed_output["text"]
    assert "did not include a final response body" in text
    assert "Read" in text
    assert "docs/index.md" in text
    assert "completed without output" not in text


def test_run_claude_code_backend_reads_nested_result_message_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    env = {**_env(tmp_path), CLAUDE_CODE_RUN_APPROVED_ENV: "1"}
    original_popen = subprocess.Popen

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.shutil.which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    class _Process:
        stdout = iter(
            [
                (
                    '{"type":"result","message":{"content":[{"type":"text",'
                    '"text":"nested final summary"}]}}\n'
                ),
            ]
        )

        def wait(self, timeout=None):
            return 0

    def _popen(args, **kwargs):
        if args[0] != "claude":
            return original_popen(args, **kwargs)
        return _Process()

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.subprocess.Popen",
        _popen,
    )

    result = dispatch_slash_command("/run --backend=claude-code Upgrade Craik Docs", env=env)

    assert result.exit_code == 0
    assert "Final output:\nnested final summary" in result.text


def test_run_claude_code_backend_records_interrupted_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    env = {**_env(tmp_path), CLAUDE_CODE_RUN_APPROVED_ENV: "1"}
    cancel_event = threading.Event()
    cancel_event.set()
    original_popen = subprocess.Popen

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.shutil.which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    class _Process:
        stdout = iter(())
        terminated = False

        def poll(self):
            return -15 if self.terminated else None

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.terminated = True

        def wait(self, timeout=None):
            return -15

    def _popen(args, **kwargs):
        if args[0] != "claude":
            return original_popen(args, **kwargs)
        return _Process()

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.subprocess.Popen",
        _popen,
    )

    with claude_code_progress(None, cancel_event=cancel_event):
        result = dispatch_slash_command("/run --backend claude-code Upgrade Craik Docs", env=env)
    inspected = dispatch_slash_command("/run inspect task_upgrade_craik_docs", env=env)

    assert result.exit_code == 0
    assert "`interrupted`" in result.text
    assert '"status": "interrupted"' in inspected.text
    assert "Claude Code run interrupted by operator." in inspected.text


def test_run_claude_code_backend_observes_runtime_approval_event_without_intercepting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    env = {**_env(tmp_path), CLAUDE_CODE_RUN_APPROVED_ENV: "1"}
    original_popen = subprocess.Popen

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.shutil.which",
        lambda command: "/usr/local/bin/claude" if command == "claude" else None,
    )

    class _Process:
        stdout = iter(
            [
                (
                    '{"type":"approval_request","tool_name":"Edit",'
                    '"target":"docs/index.md","reason":"write docs"}\n'
                ),
                '{"type":"result","result":"approved path continued"}\n',
            ]
        )

        def wait(self, timeout=None):
            return 0

    def _popen(args, **kwargs):
        if args[0] != "claude":
            return original_popen(args, **kwargs)
        return _Process()

    monkeypatch.setattr(
        "craik.runtime.shell.contract_runtime.builtin_slash_commands.subprocess.Popen",
        _popen,
    )

    result = dispatch_slash_command("/run --backend claude-code Upgrade Craik Docs", env=env)

    store = LocalStore.from_env(env)
    try:
        output = store.get_run_output("runout_upgrade_craik_docs_claude_code")
    finally:
        store.close()

    assert result.exit_code == 0
    assert output is not None
    activity = output.observed_output["activity"]
    assert activity["runtime_approvals"]
    assert output.observed_output["progress_events"][0].startswith(
        "Claude Code requests approval"
    )
    assert output.observed_output["text"] == "approved path continued"


def test_run_claude_code_backend_requires_operator_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    env = _env(tmp_path)

    result = dispatch_slash_command("/run --backend claude-code Upgrade Craik Docs", env=env)
    runs = dispatch_slash_command("/run list", env=env)

    assert result.exit_code == 2
    assert "requires operator approval" in result.text
    assert "task_upgrade_craik_docs" not in runs.text


def test_run_claude_code_backend_does_not_treat_tui_marker_as_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    monkeypatch.chdir(repo)
    env = {**_env(tmp_path), "CRAIK_TUI": "1"}

    result = dispatch_slash_command("/run --backend claude-code Upgrade Craik Docs", env=env)

    assert result.exit_code == 2
    assert "requires operator approval" in result.text


def test_craik_prefix_gets_specific_recovery() -> None:
    result = dispatch_slash_command("/craik auth login openai", env={})

    assert (
        result.text
        == "Drop the `craik` prefix — try `/auth login openai` instead. "
        "`/help` lists all slash commands."
    )


def test_unknown_command_suggests_close_candidate() -> None:
    result = dispatch_slash_command("/auht login", env={})

    assert result.text == "unknown slash command: /auht. Did you mean `/auth login`?"


def _claude_cli_marker_profile() -> AuthProfile:
    return AuthProfile(
        id="anthropic:default",
        kind=CredentialKind.MARKER,
        provider_family="anthropic",
        metadata={"external_runtime": "claude-cli", "credential_mode": "claude-cli"},
        created_at=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
        last_status="ok",
    )
