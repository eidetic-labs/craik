from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import click
import pytest
from typer.testing import CliRunner

from craik.cli import app
from craik.contracts.models import (
    DocsProfile,
    EvidenceReference,
    HandoffQualityScore,
    HumanDelegationPoint,
    InstructionSource,
    KnownTrap,
    MemoryProfile,
    ProjectProfile,
    QualityScoreComponent,
    RepoProfile,
    TaskRequest,
)
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore

runner = CliRunner()


@pytest.mark.parametrize(
    "args",
    [
        ["operator", "evidence"],
        ["operator", "delegations"],
        ["operator", "instructions"],
        ["operator", "quality"],
        ["operator", "traps"],
    ],
)
def test_project_scoped_operator_commands_require_project_on_multi_project_home(
    tmp_path: Path,
    args: list[str],
) -> None:
    home = tmp_path / "home"
    _seed_projects(home)
    _put_operator_session(home)

    result = runner.invoke(app, args, env={"CRAIK_HOME": str(home)})

    assert result.exit_code != 0
    assert (
        "--project required when multiple projects are registered"
        in click.unstyle(result.output)
    )


@pytest.mark.parametrize(
    ("args", "included", "excluded"),
    [
        (
            ["operator", "evidence", "--project", "project_alpha"],
            "Evidence alpha",
            "Evidence beta",
        ),
        (
            ["operator", "delegations", "--project", "project_alpha", "--all"],
            "delegation_alpha",
            "delegation_beta",
        ),
        (
            ["operator", "instructions", "--project", "project_alpha"],
            "source_alpha",
            "source_beta",
        ),
        (
            ["operator", "quality", "--project", "project_alpha"],
            "quality_alpha",
            "quality_beta",
        ),
        (
            ["operator", "traps", "--project", "project_alpha"],
            "trap_alpha",
            "trap_beta",
        ),
    ],
)
def test_project_scoped_operator_commands_filter_to_requested_project(
    tmp_path: Path,
    args: list[str],
    included: str,
    excluded: str,
) -> None:
    home = tmp_path / "home"
    _seed_projects(home)
    _put_operator_session(home)
    _seed_scoped_records(home)

    result = runner.invoke(app, args, env={"CRAIK_HOME": str(home)})

    assert result.exit_code == 0
    assert included in result.output
    assert excluded not in result.output


def test_operator_delegations_default_to_current_operator_and_unassigned(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    _seed_projects(home)
    _put_operator_session(home)
    _seed_scoped_records(home)

    scoped = runner.invoke(
        app,
        ["operator", "delegations", "--project", "project_alpha"],
        env={"CRAIK_HOME": str(home)},
    )
    all_items = runner.invoke(
        app,
        ["operator", "delegations", "--project", "project_alpha", "--all"],
        env={"CRAIK_HOME": str(home)},
    )

    assert scoped.exit_code == 0
    assert "delegation_alpha" in scoped.output
    assert "delegation_other" not in scoped.output
    assert all_items.exit_code == 0
    assert "delegation_other" in all_items.output


def test_operator_instructions_auto_scopes_single_project_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _seed_projects(home, project_ids=("project_alpha",))
    _put_operator_session(home)
    _seed_instruction_source(home, "project_alpha", "source_alpha")

    result = runner.invoke(
        app,
        ["operator", "instructions", "--json"],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert [source["id"] for source in payload["sources"]] == ["source_alpha"]


def _seed_projects(
    home: Path,
    *,
    project_ids: tuple[str, ...] = ("project_alpha", "project_beta"),
) -> None:
    store = LocalStore.from_paths(ensure_craik_home({"CRAIK_HOME": str(home)}))
    try:
        store.initialize()
        for project_id in project_ids:
            suffix = project_id.removeprefix("project_")
            store.put_project(
                ProjectProfile(
                    id=project_id,
                    name=suffix,
                    repo=RepoProfile(type="git", local_path=f"/tmp/{project_id}"),
                    docs=DocsProfile(),
                    memory=MemoryProfile(backend="local", scope="local"),
                )
            )
            store.put_task(
                TaskRequest(
                    id=f"task_{suffix}",
                    title=f"{suffix} task",
                    objective=f"Inspect {suffix}.",
                    project_id=project_id,
                    requested_by="operator",
                    mode="implement",
                    created_at=datetime(2026, 5, 21, tzinfo=UTC),
                )
            )
    finally:
        store.close()


def _seed_scoped_records(home: Path) -> None:
    store = LocalStore.from_paths(ensure_craik_home({"CRAIK_HOME": str(home)}))
    try:
        store.initialize()
        for project_id, suffix in (
            ("project_alpha", "alpha"),
            ("project_beta", "beta"),
        ):
            task_id = f"task_{suffix}"
            store.put_evidence(
                EvidenceReference(
                    id=f"evidence_{suffix}",
                    source="tests",
                    kind="command",
                    locator="uv run pytest",
                    summary=f"Evidence {suffix}",
                    metadata={"project_id": project_id, "task_id": task_id},
                )
            )
            store.put_human_delegation(
                HumanDelegationPoint(
                    id=f"delegation_{suffix}",
                    task_id=task_id,
                    kind="approval",
                    status="open",
                    summary=f"Delegate {suffix}.",
                    requested_decision=f"Approve {suffix}.",
                    requested_by="agent:codex",
                    owner="operator-123",
                    created_at=datetime(2026, 5, 21, tzinfo=UTC),
                )
            )
            _seed_instruction_source(home, project_id, f"source_{suffix}")
            store.put_handoff_quality_score(
                HandoffQualityScore(
                    id=f"quality_{suffix}",
                    task_id=task_id,
                    project_id=project_id,
                    handoff_id=f"handoff_{suffix}",
                    score=0.9,
                    band="excellent",
                    components=[
                        QualityScoreComponent(
                            name="summary",
                            score=0.9,
                            weight=1.0,
                            rationale="Summary is complete.",
                        )
                    ],
                    created_at=datetime(2026, 5, 21, tzinfo=UTC),
                )
            )
            store.put_known_trap(
                KnownTrap(
                    id=f"trap_{suffix}",
                    project_id=project_id,
                    task_id=task_id,
                    kind="workflow",
                    status="active",
                    statement=f"Trap {suffix}.",
                    avoidance=f"Avoid {suffix}.",
                    evidence_ids=[f"evidence_{suffix}"],
                    created_at=datetime(2026, 5, 21, tzinfo=UTC),
                )
            )
        store.put_human_delegation(
            HumanDelegationPoint(
                id="delegation_other",
                task_id="task_alpha",
                kind="approval",
                status="open",
                summary="Delegate other.",
                requested_decision="Approve other.",
                requested_by="agent:codex",
                owner="operator-other",
                created_at=datetime(2026, 5, 21, tzinfo=UTC),
            )
        )
    finally:
        store.close()


def _seed_instruction_source(home: Path, project_id: str, source_id: str) -> None:
    store = LocalStore.from_paths(ensure_craik_home({"CRAIK_HOME": str(home)}))
    try:
        store.initialize()
        if store.get_instruction_source(source_id) is None:
            store.put_instruction_source(
                InstructionSource(
                    id=source_id,
                    project_id=project_id,
                    kind="agents_md",
                    path="AGENTS.md",
                    owner="repo",
                    declared_by="operator-123",
                    created_at=datetime(2026, 5, 21, tzinfo=UTC),
                )
            )
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
