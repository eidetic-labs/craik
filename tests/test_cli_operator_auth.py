from pathlib import Path

import pytest
from typer.testing import CliRunner

from craik.cli import app

runner = CliRunner()


@pytest.mark.parametrize(
    "args",
    [
        ["operator", "overview"],
        ["operator", "work-graph"],
        ["operator", "handoff", "handoff_missing"],
        ["operator", "receipt", "receipt_missing"],
        ["operator", "contradictions"],
        ["operator", "evidence"],
        ["operator", "delegations"],
        ["operator", "budget"],
        ["operator", "instructions"],
        ["operator", "quality"],
        ["operator", "memory-impact", "preview_missing"],
        ["operator", "traps"],
        ["operator", "run-delta", "run_delta_missing"],
    ],
)
def test_operator_commands_require_active_session(
    tmp_path: Path,
    args: list[str],
) -> None:
    result = runner.invoke(app, args, env={"CRAIK_HOME": str(tmp_path / "home")})

    assert result.exit_code == 2
    assert "active operator session required; run craik login" in result.output


@pytest.mark.parametrize(
    "args",
    [
        [
            "agent-message",
            "send",
            "--task-id",
            "task_1",
            "--from-agent",
            "agent:a",
            "--to-agent",
            "agent:b",
            "--subject",
            "s",
            "--body",
            "b",
            "--run-id",
            "run_1",
        ],
        ["agent-message", "receive", "message_1", "--received-by", "agent:b"],
        ["auth", "list"],
        ["auth", "add", "openai:work", "--kind", "api-key", "--env-var", "OPENAI_API_KEY"],
        ["auth", "setup", "local"],
        ["auth", "remove", "openai:work"],
        ["auth", "test", "openai:work"],
        ["auth", "approve", "openai:work", "--run", "run_1"],
        ["auth", "grant", "openai:work", "--to-subject", "operator-123"],
        ["auth", "status"],
        ["delegation", "pause", "run_1", "--summary", "s", "--decision", "d"],
        [
            "delegation",
            "resolve",
            "delegation_1",
            "--resolution",
            "ok",
            "--operator-subject",
            "operator-123",
            "--operator-issuer",
            "issuer",
        ],
        ["handoff", "create", "task_1", "--summary", "s"],
        ["handoff", "show", "handoff_1"],
        ["prompt", "compile", "task_1", "--runner", "fixture"],
        ["project", "add", "."],
        ["project", "list"],
        ["project", "show", "project_1"],
        ["task", "create", "--title", "t", "--objective", "o", "--project", "project_1"],
        ["intent", "show", "intent_1"],
        ["case", "build", "task_1"],
        ["case", "show", "case_1"],
        ["contradictions", "open", "--summary", "s", "--fact", "a", "--fact", "b"],
        ["contradictions", "list"],
        ["contradictions", "show", "contradiction_1"],
        ["graph", "export"],
        [
            "memory",
            "propose",
            "task_1",
            "--entity",
            "e",
            "--relation",
            "r",
            "--value",
            "v",
            "--source",
            "s",
            "--evidence-source",
            "src",
            "--evidence-locator",
            "loc",
            "--evidence-summary",
            "sum",
        ],
        ["memory", "list"],
        ["memory", "show", "proposal_1"],
        ["memory", "approve", "proposal_1"],
        ["memory", "reject", "proposal_1"],
        ["memory", "search", "query"],
        ["memory", "diff", "task_1"],
        ["memory", "preview", "task_1"],
        ["receipts", "list"],
        ["receipts", "show", "receipt_1"],
        ["references", "list"],
        ["references", "verify", "reference_1"],
        [
            "review",
            "critic",
            "task_1",
            "--finding-type",
            "bug",
            "--summary",
            "s",
            "--rationale",
            "r",
        ],
        [
            "review",
            "red-team",
            "task_1",
            "--finding-type",
            "attack",
            "--summary",
            "s",
            "--attack-path",
            "p",
        ],
        ["run", "execute", "task_1"],
        ["run", "list"],
        ["run", "inspect", "run_1"],
        ["run", "show", "run_1"],
        ["run", "resume", "run_1"],
        ["run", "cancel", "run_1"],
        ["run", "recover", "run_1"],
        ["run", "delta", "run_delta_1"],
        [
            "scope-change",
            "decide",
            "scope_1",
            "--decision",
            "denied",
            "--rationale",
            "r",
            "--decided-by",
            "operator-123",
        ],
        ["skills", "list"],
        ["skills", "show", "skill_1"],
        [
            "task",
            "resume",
            "--from-handoff",
            "handoff_1",
            "--auth-profile-id",
            "openai:work",
            "--operator-subject",
            "operator-123",
            "--operator-issuer",
            "issuer",
        ],
    ],
)
def test_stateful_cli_commands_require_active_session(
    tmp_path: Path,
    args: list[str],
) -> None:
    result = runner.invoke(app, args, env={"CRAIK_HOME": str(tmp_path / "home")})

    assert result.exit_code == 2
    assert "active operator session required; run craik login" in result.output
