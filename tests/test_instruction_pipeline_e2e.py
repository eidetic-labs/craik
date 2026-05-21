import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.paths import ensure_craik_home
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.projects.prompts import PromptCompiler
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import CaseFileAssembler
from craik.runtime.work.tasks import create_task

runner = CliRunner()


def test_instruction_pipeline_cli_e2e_reaches_prompt_with_stale_and_conflict(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    repo = _repo(tmp_path)
    env = {"CRAIK_HOME": str(home)}
    project_id = _seed_project(home, repo)
    _put_operator_session(home)

    for command in (
        ["instructions", "register", "agents_md", "AGENTS.md", "--project", project_id],
        [
            "instructions",
            "register",
            "policy_doc",
            "docs/allow.md",
            "--project",
            project_id,
        ],
    ):
        result = runner.invoke(app, command, env=env)
        assert result.exit_code == 0, result.output

    first_ingest = runner.invoke(
        app,
        ["instructions", "ingest", "--project", project_id, "--json"],
        env=env,
    )
    first_payload = json.loads(first_ingest.stdout)
    assert first_ingest.exit_code == 0, first_ingest.output
    assert first_payload["proposal_count"] == 2

    first_command = _proposal_by_statement(
        home,
        "Run pytest before release.",
    )
    approved_old = runner.invoke(
        app,
        [
            "instructions",
            "approve",
            first_command["id"],
            "--rationale",
            "Initial command applies.",
        ],
        env=env,
    )
    assert approved_old.exit_code == 0, approved_old.output

    (repo / "AGENTS.md").write_text(
        "- Run pytest before release.\n- Always ensure docs pass.\n",
        encoding="utf-8",
    )
    (repo / "docs" / "deny.md").write_text(
        "Deny tool shell.\n",
        encoding="utf-8",
    )
    registered_deny = runner.invoke(
        app,
        [
            "instructions",
            "register",
            "policy_doc",
            "docs/deny.md",
            "--project",
            project_id,
        ],
        env=env,
    )
    second_ingest = runner.invoke(
        app,
        ["instructions", "ingest", "--project", project_id, "--json"],
        env=env,
    )
    second_payload = json.loads(second_ingest.stdout)

    assert registered_deny.exit_code == 0, registered_deny.output
    assert second_ingest.exit_code == 0, second_ingest.output
    assert second_payload["invalidated_count"] >= 1
    assert second_payload["contradiction_count"] >= 1

    fresh_instruction = _proposal_by_statement(home, "Always ensure docs pass.")
    approved_new = runner.invoke(
        app,
        [
            "instructions",
            "approve",
            fresh_instruction["id"],
            "--rationale",
            "Fresh instruction applies.",
        ],
        env=env,
    )
    assert approved_new.exit_code == 0, approved_new.output

    store = _store(home)
    try:
        task = create_task(
            store,
            title="Apply distilled instructions",
            objective="Use active distilled instructions.",
            project_id=project_id,
        )
        CaseFileAssembler(store).build(task.id)
        prompt = PromptCompiler(store).compile(task.id, runner_id="codex")
    finally:
        store.close()

    section = _section_body(prompt.prompt, "Active instruction constraints")
    assert prompt.prompt.count("## Active instruction constraints") == 1
    assert "Always ensure docs pass." in section
    assert "Run pytest before release." not in section
    assert any(
        "Stale governing distillation excluded" in item
        for item in prompt.distillation_warnings
    )


def _proposal_by_statement(home: Path, statement: str) -> dict[str, object]:
    result = runner.invoke(
        app,
        ["instructions", "list", "--json"],
        env={"CRAIK_HOME": str(home)},
    )
    assert result.exit_code == 0, result.output
    for proposal in json.loads(result.stdout):
        if proposal["statement"] == statement and proposal["status"] == "proposed":
            return proposal
    raise AssertionError(f"missing proposed instruction: {statement}")


def _section_body(prompt: str, title: str) -> str:
    marker = f"## {title}\n"
    start = prompt.index(marker) + len(marker)
    next_section = prompt.find("\n\n## ", start)
    return prompt[start:] if next_section == -1 else prompt[start:next_section]


def _seed_project(home: Path, repo: Path) -> str:
    store = _store(home)
    try:
        return ProjectRegistry(store).add_project(repo, name="Example").id
    finally:
        store.close()


def _store(home: Path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    store = LocalStore.from_paths(paths)
    store.initialize()
    return store


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


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "AGENTS.md").write_text("- Run pytest before release.\n", encoding="utf-8")
    (repo / "docs" / "allow.md").write_text("Allow tool shell.\n", encoding="utf-8")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "AGENTS.md", "docs")
    _run_git(repo, "commit", "-m", "initial")
    return repo


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ("git", *args),
        cwd=repo,
        check=True,
        env={
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_AUTHOR_NAME": "Craik Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Craik Test",
        },
    )
