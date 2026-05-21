import subprocess
from pathlib import Path

from craik.contracts.models import (
    DistilledInstructionProposal,
    InstructionProvenance,
    PromotedInstructionConstraint,
)
from craik.runtime.instruction_approval import approve_instruction, reject_instruction
from craik.runtime.instruction_distillation import ingest_project_instructions
from craik.runtime.instructions import register_source
from craik.runtime.paths import ensure_craik_home
from craik.runtime.projects.instruction_sources import active_instruction_context
from craik.runtime.projects.onboarding import AgentOnboardingBuilder
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.projects.prompts import PromptCompiler
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import CaseFileAssembler
from craik.runtime.work.handoffs import HandoffWriter
from craik.runtime.work.tasks import create_task


def _store(tmp_path: Path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    return store


def test_approved_distillations_reach_case_file_prompt_onboarding_and_handoff(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    try:
        repo = _repo(tmp_path)
        project = ProjectRegistry(store).add_project(repo, name="Docs")
        task = create_task(
            store,
            title="Apply instructions",
            objective="Use approved instructions.",
            project_id=project.id,
        )
        _approved_constraint(store, project.id)

        case_file = CaseFileAssembler(store).build(task.id)
        prompt = PromptCompiler(store).compile(task.id, runner_id="codex")
        onboarding = AgentOnboardingBuilder(store).build(project.id)
        handoff = HandoffWriter(store).create(
            task_id=task.id,
            agent="agent:test",
            summary="Applied instruction context.",
            tests_run=["pytest"],
        )

        active = active_instruction_context(store, project.id)
        assert active[0]["statement"] == "Run tests before merge."
        assert case_file.context_budget["active_instruction_constraints"] == active
        assert "Run tests before merge." in prompt.prompt
        assert onboarding.project_model["active_instruction_constraints"] == active
        assert any("constraint_distilled_instruction" in item for item in handoff.context_debt)
    finally:
        store.close()


def test_unapproved_stale_or_contradicted_distillations_are_inactive(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        repo = _repo(tmp_path)
        project = ProjectRegistry(store).add_project(repo, name="Docs")
        task = create_task(
            store,
            title="Ignore inactive",
            objective="Ignore inactive instructions.",
            project_id=project.id,
        )
        store.put_distilled_instruction_proposal(
            _proposal(project.id, status="proposed", contradiction_ids=["contradiction_one"])
        )
        store.put_distilled_instruction_proposal(_proposal(project.id, status="deferred"))
        CaseFileAssembler(store).build(task.id)

        assert active_instruction_context(store, project.id) == []
    finally:
        store.close()


def test_case_file_loads_governing_distillations_with_provenance_and_receipt(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    try:
        repo = _repo(tmp_path)
        project = ProjectRegistry(store).add_project(repo, name="Docs")
        task = create_task(
            store,
            title="Load distillations",
            objective="Use governing distillations.",
            project_id=project.id,
        )
        (repo / "AGENTS.md").write_text("- Run tests before merge.\n", encoding="utf-8")
        register_source(
            store,
            project_id=project.id,
            kind="agents_md",
            owner="team:runtime",
            registered_by="agent:test",
        )
        ingest_project_instructions(store, project.id)
        proposal = store.list_distilled_instruction_proposals()[0]
        approval = approve_instruction(
            store,
            proposal_id=proposal.id,
            operator_identity="user:maintainer",
            rationale="Valid project instruction.",
        )

        case_file = CaseFileAssembler(store).build(task.id)

        assert len(case_file.distillations) == 1
        entry = case_file.distillations[0]
        assert entry["id"] == proposal.id
        assert entry["category"] == "command"
        assert entry["source_id"] == proposal.source_id
        assert entry["approval_receipt"]["id"] == approval.review.id
        assert entry["provenance"][0]["path"] == "AGENTS.md"
        assert entry["provenance"][0]["start_line"] == 1
        assert case_file.context_budget["distillations"] == case_file.distillations
    finally:
        store.close()


def test_case_file_removes_rejected_or_superseded_distillations_from_new_builds(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    try:
        repo = _repo(tmp_path)
        project = ProjectRegistry(store).add_project(repo, name="Docs")
        task = create_task(
            store,
            title="Refresh distillations",
            objective="Refresh governing distillations.",
            project_id=project.id,
        )
        first = _proposal(
            project.id,
            status="proposed",
            proposal_id="distilled_instruction_first",
        )
        second = _proposal(
            project.id,
            status="proposed",
            proposal_id="distilled_instruction_second",
        )
        for proposal in (first, second):
            store.put_distilled_instruction_proposal(proposal)
            store.put_instruction_provenance(
                InstructionProvenance(
                    id=proposal.provenance_ids[0],
                    project_id=project.id,
                    source_id=proposal.source_id,
                    snapshot_id=proposal.snapshot_id,
                    path="AGENTS.md",
                    start_line=1,
                    end_line=1,
                    summary=proposal.statement,
                    captured_at=proposal.created_at,
                )
            )
        approve_instruction(
            store,
            proposal_id=first.id,
            operator_identity="user:maintainer",
            rationale="Initial approval.",
        )
        first_case = CaseFileAssembler(store).build(task.id)
        reject_instruction(
            store,
            proposal_id=first.id,
            operator_identity="user:maintainer",
            rationale="Revoked.",
        )
        approve_instruction(
            store,
            proposal_id=second.id,
            operator_identity="user:maintainer",
            rationale="Replacement.",
        )
        second_case = CaseFileAssembler(store).build(task.id)

        assert [item["id"] for item in first_case.distillations] == [first.id]
        assert [item["id"] for item in second_case.distillations] == [second.id]
    finally:
        store.close()


def test_case_file_orders_governing_distillations_by_category(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        repo = _repo(tmp_path)
        project = ProjectRegistry(store).add_project(repo, name="Docs")
        task = create_task(
            store,
            title="Order distillations",
            objective="Order governing distillations.",
            project_id=project.id,
        )
        preference = _proposal(
            project.id,
            status="proposed",
            proposal_id="distilled_instruction_a_preference",
            category="preference",
        )
        policy = _proposal(
            project.id,
            status="proposed",
            proposal_id="distilled_instruction_z_policy",
            category="policy",
        )
        for proposal in (preference, policy):
            store.put_distilled_instruction_proposal(proposal)
            store.put_instruction_provenance(
                InstructionProvenance(
                    id=proposal.provenance_ids[0],
                    project_id=project.id,
                    source_id=proposal.source_id,
                    snapshot_id=proposal.snapshot_id,
                    path="AGENTS.md",
                    start_line=1,
                    end_line=1,
                    summary=proposal.statement,
                    captured_at=proposal.created_at,
                )
            )
            approve_instruction(
                store,
                proposal_id=proposal.id,
                operator_identity="user:maintainer",
                rationale="Valid project instruction.",
            )

        case_file = CaseFileAssembler(store).build(task.id)

        assert [item["category"] for item in case_file.distillations] == [
            "policy",
            "preference",
        ]
    finally:
        store.close()


def _approved_constraint(store: LocalStore, project_id: str) -> None:
    proposal = _proposal(
        project_id,
        status="governing",
        promoted_constraint_id="constraint_distilled_instruction",
    )
    store.put_distilled_instruction_proposal(proposal)
    store.put_promoted_instruction_constraint(
        PromotedInstructionConstraint(
            id="constraint_distilled_instruction",
            project_id=project_id,
            proposal_id=proposal.id,
            source_id=proposal.source_id,
            snapshot_id=proposal.snapshot_id,
            category=proposal.category,
            statement=proposal.statement,
            provenance_ids=proposal.provenance_ids,
            evidence_ids=proposal.evidence_ids,
            active=True,
            created_at="2026-05-15T22:31:00Z",
        )
    )


def _proposal(
    project_id: str,
    *,
    status: str,
    proposal_id: str = "distilled_instruction",
    category: str = "command",
    promoted_constraint_id: str | None = None,
    contradiction_ids: list[str] | None = None,
) -> DistilledInstructionProposal:
    return DistilledInstructionProposal(
        id=proposal_id,
        project_id=project_id,
        source_id="instruction_source_agents_md",
        snapshot_id="snapshot_agents",
        category=category,
        statement="Run tests before merge.",
        rationale="Extracted from AGENTS.md.",
        confidence=0.9,
        provenance_ids=["provenance_agents_rule"],
        evidence_ids=["evidence_agents_rule"],
        contradiction_ids=contradiction_ids or [],
        promotion_status=status,
        promoted_constraint_id=promoted_constraint_id,
        decided_by="user:maintainer" if status != "proposed" else None,
        decided_at="2026-05-15T22:31:00Z" if status != "proposed" else None,
        created_at="2026-05-15T22:30:00Z",
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "README.md").write_text("# Example\n")
    (repo / "docs" / "guide.md").write_text("# Guide\n")
    (repo / "docs" / "adr" / "0001.md").write_text("# ADR\n")
    (repo / "pyproject.toml").write_text("[project]\nname = \"example\"\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md", "docs", "pyproject.toml")
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
