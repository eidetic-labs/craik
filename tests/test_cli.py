import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from craik import __version__
from craik.cli import app, package_version
from craik.cli import receipts_app as mounted_receipts_app
from craik.cli_receipts import receipts_app
from craik.contracts.models import (
    CapabilityReceipt,
    ContextDebtRecord,
    DistilledInstructionProposal,
    Handoff,
    InstructionProvenance,
    IntentLock,
    ReceiptResult,
    RecoverySession,
    RunDelta,
    RunDeltaItem,
    RunOutput,
    ScopeChangeRequest,
    TaskRun,
    TaskRunStatus,
)
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.paths import ensure_craik_home
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.store import LocalStore
from craik.runtime.work.receipts import ReceiptStore
from craik.runtime.work.tasks import create_task

runner = CliRunner()


def test_package_import_exposes_version() -> None:
    assert package_version() == __version__


def test_version_option_prints_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == package_version()


def test_receipts_app_is_mounted_from_extracted_module() -> None:
    result = runner.invoke(app, ["receipts", "--help"])

    assert mounted_receipts_app is receipts_app
    assert result.exit_code == 0
    assert "Inspect persisted capability receipts." in result.output


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (["auth", "--help"], "add"),
        (["agent-message", "--help"], "send"),
        (["connect", "--help"], "stigmem"),
        (["demo", "--help"], "stigmem-docs"),
        (["handoff", "--help"], "create"),
        (["operator", "--help"], "overview"),
        (["plugins", "--help"], "grant"),
        (["references", "--help"], "verify"),
        (["scope-change", "--help"], "decide"),
        (["skills", "--help"], "install"),
    ],
)
def test_cli_extension_modules_register_commands(
    command: list[str],
    expected: str,
) -> None:
    result = runner.invoke(app, command)

    assert result.exit_code == 0
    assert expected in result.output


def test_knowledge_resolution_commands_require_operator_session(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["knowledge", "resolve-unknown", "unknown_missing", "--answer", "No session."],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code != 0
    assert "active operator session required; run craik auth login" in result.output


def test_knowledge_resolution_commands_link_receipts(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _put_operator_session(home)
    env = {"CRAIK_HOME": str(home)}

    unknown = runner.invoke(
        app,
        [
            "knowledge",
            "unknown",
            "task_knowledge",
            "--question",
            "Which validation proves this?",
            "--next-action",
            "Run pytest.",
        ],
        env=env,
    )
    request = runner.invoke(
        app,
        [
            "knowledge",
            "context-request",
            "task_knowledge",
            "--question",
            "Need current validation state.",
            "--needed-for",
            "Release readiness.",
        ],
        env=env,
    )
    debt_id = "context_debt_task_knowledge_missing_external_state_github"
    paths = ensure_craik_home(env)
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        store.put_context_debt_record(
            ContextDebtRecord(
                id=debt_id,
                task_id="task_knowledge",
                kind="missing_external_state",
                summary="GitHub state was not loaded.",
                next_action="Refresh GitHub state.",
                created_at=datetime(2026, 5, 16, 9, 10, tzinfo=UTC),
            )
        )
    finally:
        store.close()

    assert unknown.exit_code == 0
    assert request.exit_code == 0
    unknown_id = json.loads(unknown.stdout)["id"]
    request_id = json.loads(request.stdout)["id"]

    resolved_unknown = runner.invoke(
        app,
        [
            "knowledge",
            "resolve-unknown",
            unknown_id,
            "--answer",
            "The v0.5 pipeline test proves it.",
        ],
        env=env,
    )
    fulfilled_request = runner.invoke(
        app,
        ["knowledge", "fulfill-context-request", request_id],
        env=env,
    )
    resolved_debt = runner.invoke(
        app,
        [
            "knowledge",
            "resolve-context-debt",
            debt_id,
            "--summary",
            "GitHub state was refreshed.",
        ],
        env=env,
    )

    assert resolved_unknown.exit_code == 0
    assert fulfilled_request.exit_code == 0
    assert resolved_debt.exit_code == 0
    assert json.loads(resolved_unknown.stdout)["resolved_by_receipt_id"]
    assert json.loads(fulfilled_request.stdout)["fulfilled_by_receipt_id"]
    assert json.loads(resolved_debt.stdout)["resolved_by_receipt_id"]

    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        assert store.get_receipt(
            json.loads(resolved_unknown.stdout)["resolved_by_receipt_id"]
        ) is not None
        assert store.get_receipt(
            json.loads(fulfilled_request.stdout)["fulfilled_by_receipt_id"]
        ) is not None
        assert store.get_receipt(
            json.loads(resolved_debt.stdout)["resolved_by_receipt_id"]
        ) is not None
    finally:
        store.close()


def test_version_command_prints_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == package_version()


def test_root_help_describes_governed_runtime_substrate() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Governed agent-runtime substrate" in result.output


def test_operator_overview_cli_renders_empty_read_only_surface(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["operator", "overview"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    assert "Operator Surface" in result.output
    assert "Read-only: True" in result.output
    assert "Missing data is unavailable, not inferred." in result.output


def test_operator_work_graph_cli_renders_empty_graph(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["operator", "work-graph"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    assert "Work Graph: graph_all" in result.output
    assert "Nodes: 0" in result.output
    assert "Edges: 0" in result.output


def test_operator_work_graph_cli_rejects_unknown_task(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["operator", "work-graph", "--task-id", "task_missing"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code != 0
    assert "unknown task: task_missing" in result.output


def test_operator_handoff_cli_renders_view(tmp_path: Path) -> None:
    home = tmp_path / "home"
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        store.put_handoff(
            Handoff.model_validate(
                {
                    "id": "handoff_docs",
                    "task_id": "task_docs",
                    "project_id": "project_docs",
                    "agent": "agent:codex",
                    "status": "completed",
                    "summary": "Docs update completed.",
                    "self_audit": {
                        "schema_validated": True,
                        "redaction_reviewed": True,
                        "receipts_reviewed": True,
                        "assumptions_reviewed": True,
                        "validation_recorded": True,
                        "policy_exceptions_disclosed": True,
                        "notes": [],
                    },
                    "completed_actions": ["Updated docs."],
                    "artifacts": ["docs/reference/handoff-viewer.md"],
                    "files_changed": ["src/craik/cli_operator.py"],
                    "risks": [],
                    "next_steps": ["Open PR."],
                    "receipt_ids": ["receipt_pytest"],
                    "created_at": "2026-05-21T17:00:00Z",
                }
            )
        )
    finally:
        store.close()

    result = runner.invoke(
        app,
        ["operator", "handoff", "task_docs"],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Handoff: handoff_docs" in result.output
    assert "Summary: Docs update completed." in result.output
    assert "- receipt_pytest" in result.output


def test_operator_receipt_cli_renders_capability_receipt(tmp_path: Path) -> None:
    home = tmp_path / "home"
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        store.put_receipt(
            CapabilityReceipt.model_validate(
                {
                    "id": "receipt_docs",
                    "task_id": "task_docs",
                    "actor": "agent:codex",
                    "capability": "shell.test",
                    "target": "uv run pytest",
                    "policy_profile": "strict",
                    "reason": "Validate docs.",
                    "result": {
                        "status": "passed",
                        "summary": "Tests passed.",
                        "metadata": {"redacted": True},
                    },
                    "redacted": True,
                    "created_at": "2026-05-21T17:00:00Z",
                }
            )
        )
    finally:
        store.close()

    result = runner.invoke(
        app,
        ["operator", "receipt", "receipt_docs"],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Capability Receipt: receipt_docs" in result.output
    assert "Status: passed" in result.output
    assert "Redacted: True" in result.output


def test_schema_list_includes_task_request() -> None:
    result = runner.invoke(app, ["schema", "list"])

    assert result.exit_code == 0
    assert "craik.task_request" in result.stdout


def test_schema_show_prints_json_schema() -> None:
    result = runner.invoke(app, ["schema", "show", "craik.task_request"])

    assert result.exit_code == 0
    assert '"title": "TaskRequest"' in result.stdout


def test_runners_matrix_lists_built_in_trust_profiles() -> None:
    result = runner.invoke(app, ["runners", "matrix"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    runner_ids = {entry["runner"]["id"] for entry in payload}
    assert {
        "codex",
        "claude",
        "gemini",
        "fixture",
        "provider_anthropic",
        "provider_anthropic_messages",
        "provider_openai",
        "provider_openai_chat",
        "provider_openai_responses",
        "provider_local_openai_compatible",
    } == runner_ids


def test_runners_matrix_filters_one_runner() -> None:
    result = runner.invoke(app, ["runners", "matrix", "--runner", "codex"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema"] == "craik.runner_capability_matrix"
    assert payload["runner"]["id"] == "codex"
    assert payload["trust"]["default_grant_posture"] == "prompt-for-approval"


def test_home_show_does_not_create_home(tmp_path) -> None:
    home = tmp_path / "craik-home"

    result = runner.invoke(app, ["home", "show"], env={"CRAIK_HOME": str(home)})

    assert result.exit_code == 0
    assert str(home) in result.stdout
    assert not home.exists()


def test_home_init_creates_home_layout(tmp_path) -> None:
    home = tmp_path / "craik-home"

    result = runner.invoke(app, ["home", "init"], env={"CRAIK_HOME": str(home)})

    assert result.exit_code == 0
    assert (home / "config").is_dir()
    assert (home / "secrets").is_dir()
    assert (home / "case-files").is_dir()


def test_setup_wizard_writes_non_secret_gateway_config(tmp_path) -> None:
    home = tmp_path / "craik-home"

    result = runner.invoke(
        app,
        [
            "setup",
            "--project-id",
            "project_gateway",
            "--enable-gateway",
            "--policy-envelope-id",
            "policy_gateway",
        ],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["secrets_written"] is False
    assert payload["gateway_config"]["project_id"] == "project_gateway"
    assert payload["gateway_config"]["enabled"] is True
    assert payload["gateway_config"]["policy_envelope_id"] == "policy_gateway"
    assert "api_key" not in json.dumps(payload).lower()

    store = LocalStore.from_paths(ensure_craik_home({"CRAIK_HOME": str(home)}))
    try:
        store.initialize()
        config = store.get_gateway_config("gateway_default")
        assert config is not None
        assert config.enabled is True
        assert config.project_id == "project_gateway"
    finally:
        store.close()


def test_setup_wizard_rejects_public_gateway_bind_without_policy(tmp_path) -> None:
    result = runner.invoke(
        app,
        ["setup", "--gateway-bind-host", "0.0.0.0"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code != 0
    assert "public gateway bind requires policy_envelope_id" in result.output


def test_project_commands_round_trip_registered_repo(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "initial")
    home = tmp_path / "home"

    add = runner.invoke(
        app,
        [
            "project",
            "add",
            str(repo),
            "--name",
            "Example",
            "--docs-path",
            "README.md",
            "--immutable-path",
            "docs/adr/",
            "--discovery-include",
            "docs/archive/**",
            "--discovery-exclude",
            "docs/build/**",
        ],
        env={"CRAIK_HOME": str(home)},
    )
    listed = runner.invoke(app, ["project", "list"], env={"CRAIK_HOME": str(home)})
    shown = runner.invoke(app, ["project", "show", "Example"], env={"CRAIK_HOME": str(home)})

    assert add.exit_code == 0
    assert listed.exit_code == 0
    assert shown.exit_code == 0
    assert '"id": "project_example"' in shown.stdout
    assert '"immutable_paths": [' in shown.stdout
    assert '"discovery_include": [' in shown.stdout
    assert '"discovery_exclude": [' in shown.stdout
    assert not (repo / ".craik").exists()


def test_project_add_rejects_non_repo(tmp_path) -> None:
    result = runner.invoke(
        app,
        ["project", "add", str(tmp_path)],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code != 0
    assert "not inside a Git repository" in result.output


def test_task_and_case_commands_round_trip(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "README.md").write_text("# Repo\n")
    (repo / "docs" / "guide.md").write_text("# Guide\n")
    (repo / "docs" / "adr" / "0001-record.md").write_text("# ADR\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md", "docs")
    _run_git(repo, "commit", "-m", "initial")
    home = tmp_path / "home"

    project = runner.invoke(
        app,
        ["project", "add", str(repo), "--name", "Example"],
        env={"CRAIK_HOME": str(home)},
    )
    task = runner.invoke(
        app,
        [
            "task",
            "create",
            "--project",
            "Example",
            "--title",
            "Review docs",
            "--objective",
            "Review docs against implementation.",
            "--mode",
            "review",
        ],
        env={"CRAIK_HOME": str(home)},
    )
    built = runner.invoke(
        app,
        ["case", "build", "task_review_docs", "--discovery-exclude", "docs/guide.md"],
        env={"CRAIK_HOME": str(home)},
    )
    shown = runner.invoke(
        app,
        ["case", "show", "task_review_docs"],
        env={"CRAIK_HOME": str(home)},
    )
    prompt = runner.invoke(
        app,
        ["prompt", "compile", "task_review_docs", "--runner", "codex"],
        env={"CRAIK_HOME": str(home)},
    )
    graph = runner.invoke(
        app,
        ["graph", "export", "--task-id", "task_review_docs"],
        env={"CRAIK_HOME": str(home)},
    )

    assert project.exit_code == 0
    assert task.exit_code == 0
    assert built.exit_code == 0
    assert shown.exit_code == 0
    assert prompt.exit_code == 0
    assert graph.exit_code == 0
    task_payload = json.loads(task.stdout)
    assert task_payload["task"]["id"] == "task_review_docs"
    assert task_payload["intent_lock"]["id"] == "intent_review_docs"
    assert json.loads(built.stdout)["intent_lock_id"] == "intent_review_docs"
    assert "docs/guide.md" not in json.loads(built.stdout)["docs"]
    assert json.loads(built.stdout)["adrs"] == ["docs/adr/0001-record.md"]
    assert json.loads(shown.stdout)["id"] == "case_review_docs"
    prompt_payload = json.loads(prompt.stdout)
    assert prompt_payload["schema"] == "craik.compiled_prompt"
    assert prompt_payload["runner_id"] == "codex"
    assert "## Policy" in prompt_payload["prompt"]
    graph_payload = json.loads(graph.stdout)
    assert graph_payload["id"] == "graph_task_review_docs"
    assert "task:task_review_docs" in {node["id"] for node in graph_payload["nodes"]}


def test_contradiction_commands_open_list_show(tmp_path: Path) -> None:
    home = tmp_path / "home"

    opened = runner.invoke(
        app,
        [
            "contradictions",
            "open",
            "--summary",
            "Docs conflict with implementation.",
            "--fact",
            "fact_old",
            "--fact",
            "fact_new",
            "--task-id",
            "task_docs",
            "--affected-artifact",
            "README.md",
            "--evidence-id",
            "evidence_docs",
            "--owner",
            "user:maintainer",
        ],
        env={"CRAIK_HOME": str(home)},
    )
    report_id = json.loads(opened.stdout)["id"]
    listed = runner.invoke(
        app,
        ["contradictions", "list", "--task-id", "task_docs", "--status", "open"],
        env={"CRAIK_HOME": str(home)},
    )
    shown = runner.invoke(
        app,
        ["contradictions", "show", report_id],
        env={"CRAIK_HOME": str(home)},
    )

    assert opened.exit_code == 0
    assert listed.exit_code == 0
    assert shown.exit_code == 0
    assert [item["id"] for item in json.loads(listed.stdout)] == [report_id]
    assert json.loads(shown.stdout)["contradiction"]["id"] == report_id


def test_instruction_register_cli_is_idempotent_and_requires_operator(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    _seed_instruction_project(tmp_path, home)
    _put_operator_session(home)
    env = {"CRAIK_HOME": str(home)}

    first = runner.invoke(
        app,
        ["instructions", "register", "agents_md", "AGENTS.md", "--project", "Example"],
        env=env,
    )
    second = runner.invoke(
        app,
        ["instructions", "register", "agents_md", "AGENTS.md", "--project", "Example"],
        env=env,
    )
    missing_operator_home = tmp_path / "missing-operator-home"
    _seed_instruction_project(tmp_path, missing_operator_home, name="No Operator")
    missing_operator = runner.invoke(
        app,
        [
            "instructions",
            "register",
            "agents_md",
            "AGENTS.md",
            "--project",
            "No Operator",
        ],
        env={"CRAIK_HOME": str(missing_operator_home)},
    )

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    first_payload = json.loads(first.stdout)
    second_payload = json.loads(second.stdout)
    assert first_payload["registered"] is True
    assert second_payload["registered"] is False
    assert second_payload["source_id"] == first_payload["source_id"]
    assert second_payload["receipt_id"] == first_payload["receipt_id"]
    assert missing_operator.exit_code != 0
    assert "operator identity required" in missing_operator.output


def test_instruction_ingest_cli_runs_pipeline_and_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project = _seed_instruction_project(tmp_path, home)
    _put_operator_session(home)
    env = {"CRAIK_HOME": str(home)}
    registered = runner.invoke(
        app,
        ["instructions", "register", "agents_md", "AGENTS.md", "--project", "Example"],
        env=env,
    )

    first = runner.invoke(
        app,
        ["instructions", "ingest", "--project", project.id, "--json"],
        env=env,
    )
    second = runner.invoke(
        app,
        ["instructions", "ingest", "--project", project.id, "--json"],
        env=env,
    )
    listed = runner.invoke(app, ["instructions", "list", "--json"], env=env)

    assert registered.exit_code == 0, registered.output
    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert json.loads(first.stdout)["proposal_count"] == 1
    assert json.loads(second.stdout)["proposal_count"] == 0
    assert json.loads(second.stdout)["skipped_existing_count"] == 1
    proposals = json.loads(listed.stdout)
    assert [proposal["statement"] for proposal in proposals] == ["Run tests before merge."]


def test_instruction_list_cli_filters_and_prints_json(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project_id = _seed_instruction_project(tmp_path, home).id
    _put_instruction_proposal(
        home,
        project_id=project_id,
        proposal_id="distilled_instruction_policy",
        category="policy",
        status="proposed",
    )
    _put_instruction_proposal(
        home,
        project_id=project_id,
        proposal_id="distilled_instruction_boundary",
        category="boundary",
        status="rejected",
    )
    env = {"CRAIK_HOME": str(home)}

    table = runner.invoke(app, ["instructions", "list"], env=env)
    listed = runner.invoke(
        app,
        ["instructions", "list", "--status", "proposed", "--category", "policy", "--json"],
        env=env,
    )

    assert table.exit_code == 0, table.output
    assert "distilled_instruction_policy" in table.output
    assert listed.exit_code == 0, listed.output
    payload = json.loads(listed.stdout)
    assert [item["id"] for item in payload] == ["distilled_instruction_policy"]


def test_instruction_approve_cli_records_override_and_handles_errors(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    project_id = _seed_instruction_project(tmp_path, home).id
    _put_operator_session(home)
    _put_instruction_proposal(
        home,
        project_id=project_id,
        proposal_id="distilled_instruction_stale",
        category="policy",
        status="deferred",
        decided_by="agent:instruction-distillation",
    )
    env = {"CRAIK_HOME": str(home)}

    refused = runner.invoke(
        app,
        ["instructions", "approve", "distilled_instruction_stale", "--rationale", "Reviewed."],
        env=env,
    )
    approved = runner.invoke(
        app,
        [
            "instructions",
            "approve",
            "distilled_instruction_stale",
            "--rationale",
            "Reviewed stale source.",
            "--override",
        ],
        env=env,
    )
    missing_id = runner.invoke(app, ["instructions", "approve", "missing"], env=env)
    missing_operator_home = tmp_path / "approve-missing-operator"
    missing_operator_project = _seed_instruction_project(tmp_path, missing_operator_home).id
    _put_instruction_proposal(
        missing_operator_home,
        project_id=missing_operator_project,
        proposal_id="distilled_instruction_no_operator",
        category="command",
    )
    missing_operator = runner.invoke(
        app,
        ["instructions", "approve", "distilled_instruction_no_operator"],
        env={"CRAIK_HOME": str(missing_operator_home)},
    )

    assert refused.exit_code != 0
    assert "require --override" in refused.output
    assert approved.exit_code == 0, approved.output
    payload = json.loads(approved.stdout)
    assert payload["status"] == "governing"
    assert payload["override_stale"] is True
    assert payload["receipt_id"] == "promotion_review_distilled_instruction_stale"
    assert missing_id.exit_code != 0
    assert "unknown distilled instruction proposal" in missing_id.output
    assert missing_operator.exit_code != 0
    assert "operator identity required" in missing_operator.output


def test_instruction_reject_and_show_cli_surface_provenance(tmp_path: Path) -> None:
    home = tmp_path / "home"
    project_id = _seed_instruction_project(tmp_path, home).id
    _put_operator_session(home)
    _put_instruction_proposal(
        home,
        project_id=project_id,
        proposal_id="distilled_instruction_command",
        category="command",
    )
    env = {"CRAIK_HOME": str(home)}

    rejected = runner.invoke(
        app,
        [
            "instructions",
            "reject",
            "distilled_instruction_command",
            "--rationale",
            "Not applicable.",
        ],
        env=env,
    )
    shown = runner.invoke(
        app,
        ["instructions", "show", "distilled_instruction_command"],
        env=env,
    )
    missing_id = runner.invoke(app, ["instructions", "show", "missing"], env=env)
    missing_reject = runner.invoke(app, ["instructions", "reject", "missing"], env=env)
    missing_operator_home = tmp_path / "reject-missing-operator"
    missing_operator_project = _seed_instruction_project(tmp_path, missing_operator_home).id
    _put_instruction_proposal(
        missing_operator_home,
        project_id=missing_operator_project,
        proposal_id="distilled_instruction_reject_no_operator",
        category="command",
    )
    missing_operator = runner.invoke(
        app,
        ["instructions", "reject", "distilled_instruction_reject_no_operator"],
        env={"CRAIK_HOME": str(missing_operator_home)},
    )

    assert rejected.exit_code == 0, rejected.output
    assert json.loads(rejected.stdout)["receipt_id"] == (
        "promotion_review_distilled_instruction_command"
    )
    assert shown.exit_code == 0, shown.output
    payload = json.loads(shown.stdout)
    assert payload["status"] == "rejected"
    assert payload["provenance"][0]["quote"] == "Run tests before merge."
    assert missing_id.exit_code != 0
    assert "unknown distilled instruction proposal" in missing_id.output
    assert missing_reject.exit_code != 0
    assert "unknown distilled instruction proposal" in missing_reject.output
    assert missing_operator.exit_code != 0
    assert "operator identity required" in missing_operator.output


def test_onboard_command_prints_runner_readable_project_context(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "README.md").write_text("# Repo\n")
    (repo / "docs" / "adr" / "0001-record.md").write_text("# ADR\n")
    (repo / "pyproject.toml").write_text("[project]\nname = \"repo\"\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md", "docs", "pyproject.toml")
    _run_git(repo, "commit", "-m", "initial")
    home = tmp_path / "home"

    added = runner.invoke(
        app,
        ["project", "add", str(repo), "--name", "Example"],
        env={"CRAIK_HOME": str(home)},
    )
    onboarded = runner.invoke(
        app,
        ["onboard", "--project", "Example"],
        env={"CRAIK_HOME": str(home)},
    )

    assert added.exit_code == 0
    assert onboarded.exit_code == 0
    payload = json.loads(onboarded.stdout)
    assert payload["schema"] == "craik.agent_onboarding"
    assert payload["project_id"] == "project_example"
    assert payload["active_policy"]["profile"] == "strict"
    assert payload["docs_boundaries"]["immutable_paths"] == ["docs/adr/"]
    assert payload["validation_commands"][-1] == "uv run --python 3.12 --extra dev pytest"


def test_demo_stigmem_docs_command_runs_without_live_stigmem(tmp_path: Path) -> None:
    repo = tmp_path / "stigmem"
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "README.md").write_text("# Stigmem\n")
    (repo / "docs" / "adr" / "0001-record.md").write_text("# ADR\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md", "docs")
    _run_git(repo, "commit", "-m", "initial")

    result = runner.invoke(
        app,
        ["demo", "stigmem-docs", "--repo-path", str(repo), "--no-github"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema"] == "craik.demo.stigmem_docs_reconciliation"
    assert payload["status"] == "runnable"
    assert payload["stigmem_backend_status"]["status"] == "not_configured"
    assert [item["provider_id"] for item in payload["provider_executions"]] == [
        "provider_openai",
        "provider_anthropic",
    ]
    assert payload["next_commands"]


def test_demo_stigmem_docs_command_surfaces_provider_findings(tmp_path: Path) -> None:
    repo = tmp_path / "stigmem"
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "README.md").write_text("# Stigmem\n\nUse `MissingBridge`.\n")
    (repo / "src" / "runtime.py").write_text("class ExistingBridge:\n    pass\n")
    (repo / "docs" / "adr" / "0001-record.md").write_text("# ADR\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md", "docs", "src")
    _run_git(repo, "commit", "-m", "initial")

    result = runner.invoke(
        app,
        [
            "demo",
            "stigmem-docs",
            "--repo-path",
            str(repo),
            "--no-github",
            "--provider",
            "provider_openai_chat",
        ],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["provider_demo"]["mode"] == "fixture"
    assert payload["provider_demo"]["provider_id"] == "provider_openai_chat"
    assert payload["provider_demo"]["findings"]
    provider_result = payload["provider_demo"]["results"][0]
    assert provider_result["provider_family"] == "chat_completions"
    assert provider_result["model"]
    assert provider_result["usage"]["total_tokens"] > 0
    assert payload["provider_demo"]["receipt_ids"]
    assert "MissingBridge" in payload["findings"]["docs_code_mismatches"][0]


def test_intent_show_reports_task_intent_lock(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "initial")
    home = tmp_path / "home"
    runner.invoke(
        app,
        ["project", "add", str(repo), "--name", "Example"],
        env={"CRAIK_HOME": str(home)},
    )
    runner.invoke(
        app,
        [
            "task",
            "create",
            "--project",
            "Example",
            "--title",
            "Review docs",
            "--objective",
            "Review docs against implementation.",
            "--accepted-interpretation",
            "Review documentation only.",
            "--out-of-scope",
            "Code changes.",
        ],
        env={"CRAIK_HOME": str(home)},
    )

    shown = runner.invoke(
        app,
        ["intent", "show", "task_review_docs"],
        env={"CRAIK_HOME": str(home)},
    )

    assert shown.exit_code == 0
    payload = json.loads(shown.stdout)
    assert payload["id"] == "intent_review_docs"
    assert payload["accepted_interpretation"] == "Review documentation only."
    assert payload["out_of_scope"] == ["Code changes."]


def test_case_build_reports_missing_task(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["case", "build", "task_missing"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code != 0
    assert "unknown task: task_missing" in result.output


def test_handoff_commands_create_and_show_json_and_markdown(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "initial")
    home = tmp_path / "home"
    runner.invoke(
        app,
        ["project", "add", str(repo), "--name", "Example"],
        env={"CRAIK_HOME": str(home)},
    )
    runner.invoke(
        app,
        [
            "task",
            "create",
            "--project",
            "Example",
            "--title",
            "Review docs",
            "--objective",
            "Review docs against implementation.",
        ],
        env={"CRAIK_HOME": str(home)},
    )
    runner.invoke(app, ["case", "build", "task_review_docs"], env={"CRAIK_HOME": str(home)})

    created = runner.invoke(
        app,
        [
            "handoff",
            "create",
            "task_review_docs",
            "--summary",
            "Completed docs review.",
            "--agent",
            "agent:codex",
            "--completed-action",
            "Reviewed docs.",
            "--test-run",
            "pytest",
            "--next-step",
            "Continue handoff work.",
        ],
        env={"CRAIK_HOME": str(home)},
    )
    shown = runner.invoke(
        app,
        ["handoff", "show", "task_review_docs", "--markdown"],
        env={"CRAIK_HOME": str(home)},
    )
    resumed = runner.invoke(
        app,
        [
            "task",
            "resume",
            "--from-handoff",
            "handoff_review_docs",
            "--auth-profile-id",
            "openai:writer",
            "--operator-subject",
            "operator-b",
            "--operator-issuer",
            "https://issuer.example.test",
            "--runner",
            "codex",
            "--runner-mode",
            "prompt-handoff",
        ],
        env={"CRAIK_HOME": str(home)},
    )

    assert created.exit_code == 0
    assert json.loads(created.stdout)["id"] == "handoff_review_docs"
    assert json.loads(created.stdout)["self_audit"]["validation_recorded"] is True
    assert shown.exit_code == 0
    assert shown.stdout.startswith("# Handoff: task_review_docs")
    assert resumed.exit_code == 0
    resume_payload = json.loads(resumed.stdout)
    assert resume_payload["source_handoff"]["id"] == "handoff_review_docs"
    assert resume_payload["task"]["source_handoff_id"] == "handoff_review_docs"
    assert resume_payload["task"]["auth_profile_id"] == "openai:writer"
    assert resume_payload["task"]["operator_subject"] == "operator-b"
    assert resume_payload["run"]["status"] == "pending"
    assert resume_payload["run"]["runner_id"] == "codex"
    assert resume_payload["run"]["source_handoff_id"] == "handoff_review_docs"
    assert "- [x] Validation recorded" in shown.stdout


def test_handoff_command_group_stays_mounted_after_module_extraction() -> None:
    result = runner.invoke(app, ["handoff", "--help"])

    assert result.exit_code == 0
    assert "create" in result.stdout
    assert "show" in result.stdout


def test_demo_command_group_stays_mounted_after_module_extraction() -> None:
    result = runner.invoke(app, ["demo", "--help"])

    assert result.exit_code == 0
    assert "stigmem-docs" in result.stdout


def test_connect_and_onboard_commands_stay_mounted_after_module_extraction() -> None:
    connect_result = runner.invoke(app, ["connect", "--help"])
    onboard_result = runner.invoke(app, ["onboard", "--help"])

    assert connect_result.exit_code == 0
    assert "stigmem" in connect_result.stdout
    assert onboard_result.exit_code == 0
    assert "name to onboard" in onboard_result.stdout


def test_auth_commands_add_list_test_status_and_remove(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    env = {"CRAIK_HOME": str(home)}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")

    added = runner.invoke(
        app,
        [
            "auth",
            "add",
            "anthropic:work",
            "--kind",
            "api-key",
            "--env-var",
            "ANTHROPIC_API_KEY",
        ],
        env=env,
    )
    listed = runner.invoke(app, ["auth", "list"], env=env)
    tested = runner.invoke(app, ["auth", "test", "anthropic:work"], env=env)
    granted = runner.invoke(
        app,
        [
            "auth",
            "grant",
            "anthropic:work",
            "--to-subject",
            "operator-123",
            "--to-group",
            "prod-deploy",
            "--granted-by",
            "operator:admin",
        ],
        env=env,
    )
    status = runner.invoke(app, ["auth", "status"], env=env)
    removed = runner.invoke(app, ["auth", "remove", "anthropic:work"], env=env)
    listed_after_remove = runner.invoke(app, ["auth", "list"], env=env)

    assert added.exit_code == 0
    assert json.loads(added.stdout)["id"] == "anthropic:work"
    assert "anthropic-secret" not in listed.stdout
    assert [profile["id"] for profile in json.loads(listed.stdout)] == ["anthropic:work"]
    assert json.loads(tested.stdout)["status"]["status"] == "ok"
    granted_payload = json.loads(granted.stdout)
    assert granted_payload["authorized_operators"] == ["operator-123"]
    assert granted_payload["authorized_operator_groups"] == ["prod-deploy"]
    assert granted_payload["authorization_receipt_ids"]
    assert json.loads(status.stdout)[0]["last_status"] == "ok"
    assert json.loads(removed.stdout) == {"removed": "anthropic:work"}
    assert json.loads(listed_after_remove.stdout) == []


def test_auth_oauth_local_cli_profile_tests_against_credentials_file(tmp_path: Path) -> None:
    home = tmp_path / "home"
    credentials = tmp_path / "credentials.json"
    credentials.write_text(
        json.dumps(
            {
                "access_token": "local-access-token",
                "refresh_token": "local-refresh-token",
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    credentials.chmod(0o600)

    added = runner.invoke(
        app,
        [
            "auth",
            "add",
            "anthropic:local-cli",
            "--kind",
            "oauth-token",
            "--source",
            "local-cli",
            "--credentials-path",
            str(credentials),
        ],
        env={"CRAIK_HOME": str(home)},
    )
    tested = runner.invoke(
        app,
        ["auth", "test", "anthropic:local-cli"],
        env={"CRAIK_HOME": str(home)},
    )

    assert added.exit_code == 0
    assert json.loads(added.stdout)["metadata"]["credentials_path"] == str(credentials)
    assert tested.exit_code == 0
    assert json.loads(tested.stdout)["status"]["status"] == "ok"
    assert "local-access-token" not in tested.stdout


def test_auth_secret_ref_file_profile_uses_root_relative_secret(tmp_path: Path) -> None:
    home = tmp_path / "home"
    secrets_root = tmp_path / "secrets"
    secrets_root.mkdir()
    secret = secrets_root / "anthropic.key"
    secret.write_text("file-secret\n", encoding="utf-8")
    secret.chmod(0o600)

    added = runner.invoke(
        app,
        [
            "auth",
            "add",
            "anthropic:file",
            "--kind",
            "secret-ref",
            "--manager",
            "file",
            "--ref",
            "anthropic.key",
            "--secrets-root",
            str(secrets_root),
        ],
        env={"CRAIK_HOME": str(home)},
    )
    tested = runner.invoke(
        app,
        ["auth", "test", "anthropic:file"],
        env={"CRAIK_HOME": str(home)},
    )

    assert added.exit_code == 0
    assert json.loads(added.stdout)["metadata"]["ref"] == "anthropic.key"
    assert tested.exit_code == 0
    assert json.loads(tested.stdout)["status"]["status"] == "ok"
    assert "file-secret" not in tested.stdout


def test_auth_secret_ref_file_profile_rejects_absolute_ref(tmp_path: Path) -> None:
    added = runner.invoke(
        app,
        [
            "auth",
            "add",
            "anthropic:file",
            "--kind",
            "secret-ref",
            "--manager",
            "file",
            "--ref",
            str(tmp_path / "secret.txt"),
        ],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert added.exit_code != 0
    assert "relative to the secrets root" in added.output


def test_auth_profile_rejects_unsafe_provider_base_url(tmp_path: Path) -> None:
    added = runner.invoke(
        app,
        [
            "auth",
            "add",
            "openai:work",
            "--kind",
            "api-key",
            "--env-var",
            "OPENAI_API_KEY",
            "--base-url",
            "http://169.254.169.254/latest/meta-data/",
        ],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert added.exit_code != 0
    assert "HTTPS" in added.output


def test_auth_profile_allows_explicit_local_provider_base_url(tmp_path: Path) -> None:
    added = runner.invoke(
        app,
        [
            "auth",
            "add",
            "chat_completions:local",
            "--kind",
            "api-key",
            "--env-var",
            "LOCAL_API_KEY",
            "--base-url",
            "http://localhost:11434/v1",
            "--allow-local-base-url",
        ],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert added.exit_code == 0
    payload = json.loads(added.stdout)
    assert payload["metadata"]["base_url"] == "http://localhost:11434/v1"
    assert payload["metadata"]["allow_local_base_url"] is True


def test_memory_commands_propose_approve_and_search(tmp_path: Path) -> None:
    home = tmp_path / "home"

    proposed = runner.invoke(
        app,
        [
            "memory",
            "propose",
            "task_docs",
            "--entity",
            "repo:example",
            "--relation",
            "craik:memory",
            "--value",
            "Local proposals require review.",
            "--source",
            "README.md",
            "--evidence-source",
            "README.md",
            "--evidence-locator",
            "README.md#memory",
            "--evidence-summary",
            "README documents local proposals.",
        ],
        env={"CRAIK_HOME": str(home)},
    )
    proposal_id = json.loads(proposed.stdout)["id"]
    approved = runner.invoke(
        app,
        ["memory", "approve", proposal_id, "--decided-by", "user:reviewer"],
        env={"CRAIK_HOME": str(home)},
    )
    listed = runner.invoke(
        app,
        ["memory", "list", "--task-id", "task_docs", "--status", "approved"],
        env={"CRAIK_HOME": str(home)},
    )
    searched = runner.invoke(
        app,
        ["memory", "search", "local proposals"],
        env={"CRAIK_HOME": str(home)},
    )
    diff = runner.invoke(
        app,
        ["memory", "diff", "task_docs"],
        env={"CRAIK_HOME": str(home)},
    )
    preview = runner.invoke(
        app,
        ["memory", "preview", "task_docs"],
        env={"CRAIK_HOME": str(home)},
    )

    assert proposed.exit_code == 0
    assert approved.exit_code == 0
    assert diff.exit_code == 0
    assert preview.exit_code == 0
    assert json.loads(approved.stdout)["status"] == "approved"
    assert [proposal["id"] for proposal in json.loads(listed.stdout)] == [proposal_id]
    assert json.loads(searched.stdout)[0]["value"] == "Local proposals require review."
    assert json.loads(diff.stdout)["proposals_approved"] == [proposal_id]
    assert json.loads(preview.stdout)["scope_summary"] == {"local": 1}


def test_policy_show_defaults_to_strict() -> None:
    result = runner.invoke(app, ["policy", "show"])

    assert result.exit_code == 0
    assert '"profile": "strict"' in result.stdout
    assert '"fail_open": false' in result.stdout


def test_policy_show_requires_trusted_local_fail_open_opt_in() -> None:
    result = runner.invoke(app, ["policy", "show", "--profile", "trusted-local"])

    assert result.exit_code != 0
    assert "requires explicit" in result.output


def test_policy_show_can_include_fail_open_receipt() -> None:
    result = runner.invoke(
        app,
        [
            "policy",
            "show",
            "--profile",
            "trusted-local",
            "--trusted-local-fail-open",
            "--include-receipt",
        ],
    )

    assert result.exit_code == 0
    assert '"profile": "trusted-local"' in result.stdout
    assert '"fail_open": true' in result.stdout
    assert '"capability": "policy.fail_open"' in result.stdout


def test_policy_test_command_prints_passing_report(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["policy", "test"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema"] == "craik.policy_test_report"
    assert payload["status"] == "passed"
    assert payload["summary"]["failed"] == 0
    assert "immutable_path_requires_override_and_grant" in {
        item["name"] for item in payload["results"]
    }


def test_receipts_commands_list_and_show_persisted_receipts(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_receipt(
        home,
        _receipt(
            "receipt_docs",
            task_id="task_docs",
            metadata={
                "policy_envelope_id": "policy_docs",
                "handoff_ids": ["handoff_docs"],
            },
        ),
    )
    _seed_receipt(home, _receipt("receipt_other", task_id="task_other"))

    listed = runner.invoke(
        app,
        ["receipts", "list", "--task-id", "task_docs"],
        env={"CRAIK_HOME": str(home)},
    )
    shown = runner.invoke(
        app,
        ["receipts", "show", "receipt_docs"],
        env={"CRAIK_HOME": str(home)},
    )
    by_policy = runner.invoke(
        app,
        ["receipts", "list", "--policy-id", "policy_docs"],
        env={"CRAIK_HOME": str(home)},
    )
    by_handoff = runner.invoke(
        app,
        ["receipts", "list", "--handoff-id", "handoff_docs"],
        env={"CRAIK_HOME": str(home)},
    )

    assert listed.exit_code == 0
    assert shown.exit_code == 0
    assert by_policy.exit_code == 0
    assert by_handoff.exit_code == 0
    assert [receipt["id"] for receipt in json.loads(listed.stdout)] == ["receipt_docs"]
    assert json.loads(shown.stdout)["id"] == "receipt_docs"
    assert [receipt["id"] for receipt in json.loads(by_policy.stdout)] == ["receipt_docs"]
    assert [receipt["id"] for receipt in json.loads(by_handoff.stdout)] == ["receipt_docs"]


def test_receipts_show_reports_missing_receipt(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["receipts", "show", "receipt_missing"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code != 0
    assert "unknown receipt: receipt_missing" in result.output


def test_run_commands_inspect_persisted_run_state(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_run_state(home, status="interrupted")

    listed = runner.invoke(app, ["run", "list"], env={"CRAIK_HOME": str(home)})
    shown = runner.invoke(
        app,
        ["run", "inspect", "run_docs", "--include-outputs"],
        env={"CRAIK_HOME": str(home)},
    )
    shown_alias = runner.invoke(
        app,
        ["run", "show", "run_docs", "--include-outputs"],
        env={"CRAIK_HOME": str(home)},
    )

    assert listed.exit_code == 0
    assert shown.exit_code == 0
    assert shown_alias.exit_code == 0
    assert [item["id"] for item in json.loads(listed.stdout)] == ["run_docs"]
    payload = json.loads(shown.stdout)
    alias_payload = json.loads(shown_alias.stdout)
    assert payload["run"]["id"] == "run_docs"
    assert alias_payload == payload
    assert payload["next_allowed_action"] == "recover from the last safe boundary"
    assert payload["outputs"][0]["observed_output"] == {"status": "interrupted"}
    assert payload["receipts"][0]["id"] == "receipt_docs"


def test_run_command_group_stays_mounted_after_module_extraction() -> None:
    result = runner.invoke(app, ["run", "--help"])

    assert result.exit_code == 0
    assert "execute" in result.stdout
    assert "show" in result.stdout
    assert "resume" in result.stdout
    assert "cancel" in result.stdout
    assert "recover" in result.stdout
    assert "delta" in result.stdout


def test_run_delta_prints_operator_view_for_persisted_delta(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_run_state(home, status="interrupted")
    _seed_run_delta_state(home)
    _put_operator_session(home)

    result = runner.invoke(
        app,
        ["run", "delta", "run_delta_task_docs"],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exit_code == 0
    assert "Run Delta: run_delta_task_docs" in result.stdout
    assert "Task: task_docs" in result.stdout
    assert "Updated: 1" in result.stdout
    assert "- recovery_task_docs [changed_state] delta=run_delta_task_docs" in result.stdout


def test_run_delta_json_resolves_latest_delta_by_run_or_task(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_run_state(home, status="interrupted")
    _seed_run_delta_state(home)
    _put_operator_session(home)

    by_run = runner.invoke(
        app,
        ["run", "delta", "run_docs", "--json"],
        env={"CRAIK_HOME": str(home)},
    )
    by_task = runner.invoke(
        app,
        ["run", "delta", "task_docs", "--json"],
        env={"CRAIK_HOME": str(home)},
    )

    assert by_run.exit_code == 0
    assert by_task.exit_code == 0
    run_payload = json.loads(by_run.stdout)
    task_payload = json.loads(by_task.stdout)
    assert run_payload["schema"] == "craik.run_delta_view"
    assert run_payload["delta"]["id"] == "run_delta_task_docs"
    assert run_payload["recovery_sessions"][0]["id"] == "recovery_task_docs"
    assert task_payload == run_payload


def test_run_delta_reports_missing_delta(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["run", "delta", "run_delta_missing"],
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code != 0
    assert "unknown run delta, run, or task: run_delta_missing" in result.output


def test_run_execute_runs_provider_backed_mvp_path(tmp_path: Path) -> None:
    home = tmp_path / "home"
    task_id = _seed_provider_task(home, tmp_path)

    executed = runner.invoke(
        app,
        ["run", "execute", task_id, "--provider-id", "provider_anthropic"],
        env={"CRAIK_HOME": str(home)},
    )
    shown = runner.invoke(
        app,
        ["run", "inspect", task_id, "--include-outputs"],
        env={"CRAIK_HOME": str(home)},
    )

    assert executed.exit_code == 0
    assert shown.exit_code == 0
    payload = json.loads(executed.stdout)
    assert payload["schema"] == "craik.provider_backed_run_execution"
    assert payload["status"] == "completed"
    assert payload["provider_ids"] == ["provider_anthropic"]
    assert payload["provider_families"] == ["anthropic"]
    assert payload["handoff"]["status"] == "completed"
    assert f"craik run inspect {payload['run']['id']} --include-outputs" in payload["next_commands"]
    inspection = json.loads(shown.stdout)
    assert inspection["status"] == "completed"
    assert len(inspection["outputs"]) == 4


def test_run_execute_can_leave_blocked_grant_boundary(tmp_path: Path) -> None:
    home = tmp_path / "home"
    task_id = _seed_provider_task(home, tmp_path)

    result = runner.invoke(
        app,
        [
            "run",
            "execute",
            task_id,
            "--provider-id",
            "provider_openai",
            "--no-allow-fixture-action",
        ],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["provider_ids"] == ["provider_openai"]
    assert payload["provider_families"] == ["openai"]
    assert payload["handoff"]["status"] == "blocked"


def test_run_resume_continues_interrupted_provider_run(tmp_path: Path) -> None:
    home = tmp_path / "home"
    task_id = _seed_provider_task(home, tmp_path)

    interrupted = runner.invoke(
        app,
        [
            "run",
            "execute",
            task_id,
            "--provider-id",
            "provider_openai",
            "--max-iterations",
            "1",
        ],
        env={"CRAIK_HOME": str(home)},
    )
    resumed = runner.invoke(
        app,
        ["run", "resume", task_id, "--provider-id", "provider_openai"],
        env={"CRAIK_HOME": str(home)},
    )

    assert interrupted.exit_code == 0
    assert resumed.exit_code == 0
    interrupted_payload = json.loads(interrupted.stdout)
    resumed_payload = json.loads(resumed.stdout)
    assert interrupted_payload["status"] == "interrupted"
    assert resumed_payload["status"] == "completed"
    assert resumed_payload["run"]["id"] == interrupted_payload["run"]["id"]
    assert "run_docs" not in resumed_payload["run"]["id"]


def test_run_resume_refuses_non_interrupted_run(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_run_state(home, status="completed")

    result = runner.invoke(
        app,
        ["run", "resume", "run_docs"],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exit_code != 0
    assert "only interrupted runs can be resumed" in result.output


def test_run_cancel_interrupts_non_terminal_run(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_run_state(home, status="running")

    result = runner.invoke(
        app,
        ["run", "cancel", "run_docs", "--reason", "operator pause"],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["cancelled"] is True
    assert payload["run"]["status"] == "interrupted"
    assert payload["run"]["stop_reason"] == "operator pause"


def test_run_cancel_refuses_terminal_run(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_run_state(home, status="completed")

    result = runner.invoke(
        app,
        ["run", "cancel", "run_docs"],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exit_code != 0
    assert "terminal runs cannot be cancelled" in result.output


def test_delegation_pause_and_resolve_cli_flow(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_run_state(home, status="running")

    paused = runner.invoke(
        app,
        [
            "delegation",
            "pause",
            "run_docs",
            "--summary",
            "Need approval.",
            "--decision",
            "Approve continuation.",
            "--kind",
            "approval",
            "--owner",
            "user:maintainer",
        ],
        env={"CRAIK_HOME": str(home)},
    )

    assert paused.exit_code == 0
    paused_payload = json.loads(paused.stdout)
    assert paused_payload["run"]["status"] == "interrupted"
    assert paused_payload["delegation"]["run_id"] == "run_docs"
    assert paused_payload["delegation"]["receipt_ids"] == [paused_payload["receipt"]["id"]]

    resolved = runner.invoke(
        app,
        [
            "delegation",
            "resolve",
            paused_payload["delegation"]["id"],
            "--resolution",
            "Approved.",
            "--operator-subject",
            "operator-a",
            "--operator-issuer",
            "https://issuer.example.test",
            "--outcome",
            "accepted",
        ],
        env={"CRAIK_HOME": str(home)},
    )

    assert resolved.exit_code == 0
    resolved_payload = json.loads(resolved.stdout)
    assert resolved_payload["delegation"]["status"] == "resolved"
    assert resolved_payload["receipt"]["result"]["metadata"]["outcome"] == "accepted"
    assert resolved_payload["receipt"]["id"] in resolved_payload["run"]["receipt_ids"]


def test_agent_message_send_and_receive_cli_flow(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_agent_message_state(home)

    sent = runner.invoke(
        app,
        [
            "agent-message",
            "send",
            "--task-id",
            "task_multi_agent",
            "--from-agent",
            "agent:orchestrator",
            "--to-agent",
            "agent:verifier",
            "--subject",
            "Review patch",
            "--body",
            "Please verify the patch.",
            "--run-id",
            "run_multi_agent",
            "--from-role-id",
            "role_orchestrator",
            "--from-role-kind",
            "orchestrator",
        ],
        env={"CRAIK_HOME": str(home)},
    )

    assert sent.exit_code == 0
    sent_payload = json.loads(sent.stdout)
    assert sent_payload["from_agent"] == "agent:orchestrator"

    received = runner.invoke(
        app,
        [
            "agent-message",
            "receive",
            sent_payload["id"],
            "--received-by",
            "agent:verifier",
        ],
        env={"CRAIK_HOME": str(home)},
    )

    assert received.exit_code == 0
    received_payload = json.loads(received.stdout)
    assert received_payload["status"] == "received"
    assert len(received_payload["receipt_ids"]) == 2


def test_scope_change_decide_cli_expands_lock(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_scope_change_state(home)

    decided = runner.invoke(
        app,
        [
            "scope-change",
            "decide",
            "scope_change_run_docs_intent_docs_docs_examples",
            "--decision",
            "expand",
            "--rationale",
            "Docs examples are required.",
            "--decided-by",
            "operator-a",
            "--run-id",
            "run_docs",
        ],
        env={"CRAIK_HOME": str(home)},
    )

    assert decided.exit_code == 0
    payload = json.loads(decided.stdout)
    assert payload["result"]["protocol_decision"] == "expand"
    assert payload["updated_intent_lock"]["id"] == payload["run"]["intent_lock_id"]


def test_run_recover_prints_plan_for_interrupted_run(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_run_state(home, status="interrupted")
    _put_operator_session(home)

    result = runner.invoke(
        app,
        ["run", "recover", "task_docs", "--dry-run", "--reason", "continue docs"],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["recoverable"] is True
    assert payload["dry_run"] is True
    assert payload["resume_phase"] == "continue"
    assert payload["required_checks"] == [
        "reload task run state",
        "re-check policy grants",
        "re-check intent-lock stop conditions",
        "verify max-iteration budget",
    ]


def test_run_recover_refuses_non_interrupted_run(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_run_state(home, status="completed")

    result = runner.invoke(
        app,
        ["run", "recover", "run_docs"],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exit_code != 0
    assert "only interrupted runs can be recovered" in result.output


def _run_git(repo, *args: str) -> None:
    import subprocess

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


def _seed_receipt(home: Path, receipt: CapabilityReceipt) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        ReceiptStore(store).record_receipt(receipt)
    finally:
        store.close()


def _seed_provider_task(home: Path, tmp_path: Path) -> str:
    repo = tmp_path / "provider-repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Provider Repo\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md")
    _run_git(repo, "commit", "-m", "initial")
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        project = ProjectRegistry(store).add_project(repo, name="Provider Repo")
        task = create_task(
            store,
            title="Run provider MVP path",
            objective="Execute a provider-backed MVP runner path.",
            project_id=project.id,
            mode="implement",
            expected_outputs=["runner_step_result", "handoff"],
        )
        return task.id
    finally:
        store.close()


def _seed_run_state(home: Path, *, status: TaskRunStatus) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        store.put_task_run(
            TaskRun(
                id="run_docs",
                task_id="task_docs",
                case_file_id="case_docs",
                policy_envelope_id="policy_docs",
                runner_id="runner_fixture",
                runner_mode="fixture",
                status=status,
                phase="evaluate",
                iteration=2,
                max_iterations=5,
                started_at=datetime(2026, 5, 16, 12, 0, tzinfo=UTC),
                phase_started_at=datetime(2026, 5, 16, 12, 1, tzinfo=UTC),
                updated_at=datetime(2026, 5, 16, 12, 2, tzinfo=UTC),
                ended_at=datetime(2026, 5, 16, 12, 2, tzinfo=UTC),
                stop_reason=f"run {status}",
                receipt_ids=["receipt_docs"],
                runner_metadata=[{"runner_id": "runner_fixture", "execution_mode": "fixture"}],
            )
        )
        store.put_run_output(
            RunOutput(
                id="runout_docs",
                run_id="run_docs",
                step_result_id="runner_step_result_docs",
                task_id="task_docs",
                phase="evaluate",
                summary="Run output.",
                observed_output={"status": status},
                receipt_ids=["receipt_docs"],
                created_at=datetime(2026, 5, 16, 12, 2, tzinfo=UTC),
            )
        )
        ReceiptStore(store).record_receipt(_receipt("receipt_docs", task_id="task_docs"))
    finally:
        store.close()


def _seed_agent_message_state(home: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        store.put_task_run(
            TaskRun(
                id="run_multi_agent",
                task_id="task_multi_agent",
                case_file_id="case_multi_agent",
                policy_envelope_id="policy_multi_agent",
                runner_id="provider_openai_chat",
                runner_mode="fixture",
                role_id="role_orchestrator",
                role_kind="orchestrator",
                started_at=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
                phase_started_at=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
                updated_at=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
            )
        )
    finally:
        store.close()


def _seed_scope_change_state(home: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        store.put_intent_lock(
            IntentLock(
                id="intent_docs",
                task_id="task_docs",
                original_request="Review docs.",
                objective="Review docs.",
                accepted_interpretation="Review docs.",
                in_scope=["docs/"],
                out_of_scope=[],
                allowed_autonomy=[],
                stop_conditions=[],
                scope_change_rules=["Ask before expanding scope."],
                created_at=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
            )
        )
        store.put_task_run(
            TaskRun(
                id="run_docs",
                task_id="task_docs",
                case_file_id="case_docs",
                policy_envelope_id="policy_docs",
                intent_lock_id="intent_docs",
                runner_id="runner_fixture",
                runner_mode="fixture",
                status="interrupted",
                started_at=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
                phase_started_at=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
                updated_at=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
            )
        )
        store.put_scope_change_request(
            ScopeChangeRequest(
                id="scope_change_run_docs_intent_docs_docs_examples",
                task_id="task_docs",
                intent_lock_id="intent_docs",
                requested_by="agent:orchestrator",
                reason="Need docs examples.",
                current_scope=["docs/"],
                proposed_scope=["docs/", "docs/examples/"],
                policy_envelope_id="policy_docs",
                receipt_ids=["receipt_scope_request"],
                created_at=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
            )
        )
    finally:
        store.close()


def _seed_run_delta_state(home: Path) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        store.put_run_delta(
            RunDelta(
                id="run_delta_task_docs",
                project_id="project_docs",
                task_id="task_docs",
                previous_handoff_id="handoff_previous",
                current_handoff_id="handoff_current",
                case_file_ids=["case_docs"],
                receipt_ids=["receipt_docs"],
                contradiction_ids=["contradiction_docs"],
                active_instruction_constraint_ids=["constraint_docs"],
                changes=[
                    RunDeltaItem(
                        kind="updated",
                        entity_type="handoff",
                        entity_id="handoff_current",
                        summary="Current handoff replaced the stale recovery point.",
                        previous_ref="handoff_previous",
                        current_ref="handoff_current",
                        evidence_ids=["receipt_docs"],
                    )
                ],
                summary="One handoff changed since the previous recovery point.",
                created_at=datetime(2026, 5, 16, 12, 3, tzinfo=UTC),
            )
        )
        store.put_recovery_session(
            RecoverySession(
                id="recovery_task_docs",
                project_id="project_docs",
                task_id="task_docs",
                status="changed_state",
                run_delta_id="run_delta_task_docs",
                resume_summary="Review changed handoff before resuming.",
                required_actions=["review changed handoff"],
                stale_risks=["handoff changed since last run"],
                handoff_ids=["handoff_previous", "handoff_current"],
                case_file_ids=["case_docs"],
                receipt_ids=["receipt_docs"],
                contradiction_ids=["contradiction_docs"],
                active_instruction_constraint_ids=["constraint_docs"],
                created_at=datetime(2026, 5, 16, 12, 4, tzinfo=UTC),
            )
        )
    finally:
        store.close()


def _seed_instruction_project(
    tmp_path: Path,
    home: Path,
    *,
    name: str = "Example",
):
    repo = tmp_path / f"repo-{name.lower().replace(' ', '-')}-{home.name}"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("- Run tests before merge.\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "AGENTS.md")
    _run_git(repo, "commit", "-m", "initial")
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        return ProjectRegistry(store).add_project(repo, name=name)
    finally:
        store.close()


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


def _put_instruction_proposal(
    home: Path,
    *,
    project_id: str,
    proposal_id: str,
    category: str,
    status: str = "proposed",
    decided_by: str | None = None,
) -> None:
    paths = ensure_craik_home({"CRAIK_HOME": str(home)})
    store = LocalStore.from_paths(paths)
    try:
        store.initialize()
        provenance_id = f"provenance_{proposal_id}"
        created_at = datetime(2026, 5, 15, 22, 30, tzinfo=UTC)
        proposal = DistilledInstructionProposal(
            id=proposal_id,
            project_id=project_id,
            source_id="instruction_source_agents_md",
            snapshot_id="snapshot_agents",
            category=category,
            statement="Run tests before merge.",
            rationale="Extracted from AGENTS.md.",
            confidence=0.9,
            provenance_ids=[provenance_id],
            evidence_ids=[provenance_id],
            promotion_status=status,
            decided_by=decided_by or ("user:maintainer" if status != "proposed" else None),
            decided_at=created_at if status != "proposed" else None,
            created_at=created_at,
        )
        store.put_distilled_instruction_proposal(proposal)
        store.put_instruction_provenance(
            InstructionProvenance(
                id=provenance_id,
                project_id=project_id,
                source_id=proposal.source_id,
                snapshot_id=proposal.snapshot_id,
                path="AGENTS.md",
                start_line=1,
                end_line=1,
                summary=proposal.statement,
                captured_at=created_at,
            )
        )
    finally:
        store.close()


def _receipt(
    receipt_id: str,
    *,
    task_id: str,
    metadata: dict[str, object] | None = None,
) -> CapabilityReceipt:
    return CapabilityReceipt(
        id=receipt_id,
        task_id=task_id,
        actor="agent:codex",
        capability="shell.test",
        target="uv run pytest",
        policy_profile="strict",
        fail_open=False,
        reason="Validate receipt behavior.",
        result=ReceiptResult(
            status="passed",
            summary="Command completed.",
            metadata=metadata or {},
        ),
        redacted=True,
        created_at=datetime(2026, 5, 15, 12, 0, tzinfo=UTC),
    )
