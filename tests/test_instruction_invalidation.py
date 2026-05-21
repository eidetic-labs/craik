import subprocess
from datetime import UTC, datetime
from pathlib import Path

from craik.contracts.models import DistilledInstructionProposal, InstructionSourceSnapshot
from craik.runtime.instruction_snapshots import (
    compute_source_snapshot,
    refresh_project_snapshots,
)
from craik.runtime.instructions import register_source
from craik.runtime.paths import ensure_craik_home
from craik.runtime.projects.instruction_sources import (
    instruction_stale_risk_warnings,
    invalidate_stale_distillations,
    promotable_distilled_instructions,
)
from craik.runtime.projects.onboarding import AgentOnboardingBuilder
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.store import LocalStore
from craik.runtime.work.case_files import CaseFileAssembler
from craik.runtime.work.tasks import create_task


def _store(tmp_path: Path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    return store


def _snapshot(
    *,
    source_id: str = "instruction_source_agents_md",
    status: str = "unchanged",
    content_hash: str | None = "hash-old",
) -> InstructionSourceSnapshot:
    return InstructionSourceSnapshot(
        id=f"snapshot_{source_id}_{status}_{content_hash or 'missing'}",
        project_id="project_docs",
        source_id=source_id,
        path="AGENTS.md",
        content_hash=content_hash,
        hash_status=status,
        byte_count=10 if content_hash else None,
        line_count=2 if content_hash else None,
        captured_at="2026-05-15T22:31:00Z",
    )


def _proposal(source_id: str = "instruction_source_agents_md") -> DistilledInstructionProposal:
    return DistilledInstructionProposal(
        id=f"distilled_{source_id}",
        project_id="project_docs",
        source_id=source_id,
        snapshot_id=f"snapshot_{source_id}_unchanged_hash-old",
        category="instruction",
        statement="Follow declared instructions.",
        rationale="Extracted from declared source.",
        confidence=0.8,
        provenance_ids=["instruction_provenance_agents_rule"],
        evidence_ids=["evidence_agents"],
        created_at="2026-05-15T22:30:00Z",
    )


def test_unchanged_source_does_not_invalidate_distillations(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.put_instruction_source_snapshot(_snapshot())
        proposal = _proposal()
        store.put_distilled_instruction_proposal(proposal)

        invalidated = invalidate_stale_distillations(store, current_snapshots=[_snapshot()])

        assert invalidated == []
        assert store.get_distilled_instruction_proposal(proposal.id) == proposal
        assert promotable_distilled_instructions(store.list_distilled_instruction_proposals()) == [
            proposal
        ]
    finally:
        store.close()


def test_changed_source_defers_distillation_without_losing_provenance(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.put_instruction_source_snapshot(_snapshot())
        proposal = _proposal()
        store.put_distilled_instruction_proposal(proposal)
        changed = _snapshot(status="changed", content_hash="hash-new")

        invalidated = invalidate_stale_distillations(store, current_snapshots=[changed])

        assert [item.id for item in invalidated] == [proposal.id]
        updated = store.get_distilled_instruction_proposal(proposal.id)
        assert updated.promotion_status == "deferred"
        assert updated.provenance_ids == proposal.provenance_ids
        assert promotable_distilled_instructions([updated]) == []
    finally:
        store.close()


def test_missing_and_new_sources_mark_distillations_stale(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.put_instruction_source_snapshot(_snapshot())
        store.put_distilled_instruction_proposal(_proposal())
        store.put_distilled_instruction_proposal(_proposal("instruction_source_new"))

        invalidated = invalidate_stale_distillations(
            store,
            current_snapshots=[
                _snapshot(status="missing", content_hash=None),
                _snapshot(
                    source_id="instruction_source_new",
                    status="new",
                    content_hash="hash-new-source",
                ),
            ],
        )

        assert [proposal.id for proposal in invalidated] == [
            "distilled_instruction_source_agents_md",
            "distilled_instruction_source_new",
        ]
    finally:
        store.close()


def test_refresh_project_snapshots_tracks_file_lifecycle(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        repo = _repo(tmp_path)
        project = ProjectRegistry(store).add_project(repo, name="Docs")
        source = register_source(
            store,
            project_id=project.id,
            kind="agents_md",
            owner="team:runtime",
            registered_by="agent:test",
        ).source

        agents = repo / "AGENTS.md"
        agents.write_text("- Prefer deterministic tests.\n", encoding="utf-8")
        first = refresh_project_snapshots(store, project.id)[0]
        assert first.hash_status == "new"
        assert first.byte_count == len(b"- Prefer deterministic tests.\n")
        assert first.line_count == 1

        second = refresh_project_snapshots(store, project.id)[0]
        assert second.hash_status == "unchanged"
        assert second.content_hash == first.content_hash

        agents.write_text("- Prefer deterministic tests.\n- Update docs.\n", encoding="utf-8")
        changed = refresh_project_snapshots(store, project.id)[0]
        assert changed.hash_status == "changed"
        assert changed.content_hash != first.content_hash
        assert changed.line_count == 2

        agents.unlink()
        missing = refresh_project_snapshots(store, project.id)[0]
        assert missing.hash_status == "missing"
        assert missing.content_hash is None
        assert missing.byte_count is None
        assert missing.line_count is None

        stored = store.get_instruction_source_snapshot(missing.id)
        assert stored == missing
        assert compute_source_snapshot(
            source,
            base_dir=repo,
            previous_snapshot=missing,
        ).hash_status == "missing"
    finally:
        store.close()


def test_refresh_snapshots_feed_stale_invalidation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        repo = _repo(tmp_path)
        project = ProjectRegistry(store).add_project(repo, name="Docs")
        source = register_source(
            store,
            project_id=project.id,
            kind="agents_md",
            owner="team:runtime",
            registered_by="agent:test",
        ).source
        agents = repo / "AGENTS.md"
        agents.write_text("- Prefer deterministic tests.\n", encoding="utf-8")
        [first] = refresh_project_snapshots(store, project.id)

        proposal = _proposal(source.id).model_copy(
            update={
                "project_id": project.id,
                "snapshot_id": first.id,
                "promotion_status": "approved",
                "promoted_constraint_id": f"constraint_{source.id}",
                "decided_by": "agent:test",
                "decided_at": datetime(2026, 5, 15, 22, 30, tzinfo=UTC),
            }
        )
        store.put_distilled_instruction_proposal(
            DistilledInstructionProposal.model_validate(
                proposal.model_dump(mode="json", by_alias=True)
            )
        )

        agents.write_text("- Prefer deterministic tests.\n- Update docs.\n", encoding="utf-8")
        current = refresh_project_snapshots(store, project.id)
        invalidated = invalidate_stale_distillations(store, current_snapshots=current)

        assert [item.id for item in invalidated] == [proposal.id]
        updated = store.get_distilled_instruction_proposal(proposal.id)
        assert updated is not None
        assert updated.promotion_status == "deferred"
        assert store.get_instruction_source_snapshot(current[0].id) == current[0]
    finally:
        store.close()


def test_case_files_and_onboarding_surface_stale_instruction_warnings(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    try:
        repo = _repo(tmp_path)
        project = ProjectRegistry(store).add_project(repo, name="Docs")
        task = create_task(
            store,
            title="Review instructions",
            objective="Review stale instructions.",
            project_id=project.id,
        )
        proposal = _proposal().model_copy(update={"project_id": project.id})
        proposal = DistilledInstructionProposal.model_validate(
            proposal.model_dump(mode="json", by_alias=True)
        )
        store.put_distilled_instruction_proposal(proposal)
        invalidated = proposal.model_copy(
            update={
                "promotion_status": "deferred",
                "decided_by": "agent:instruction-distillation",
                "decided_at": datetime(2026, 5, 15, 22, 31, tzinfo=UTC),
            }
        )
        store.put_distilled_instruction_proposal(
            DistilledInstructionProposal.model_validate(
                invalidated.model_dump(mode="json", by_alias=True)
            )
        )

        warnings = instruction_stale_risk_warnings(store, project.id)
        case_file = CaseFileAssembler(store).build(task.id)
        onboarding = AgentOnboardingBuilder(store).build(project.id)

        assert warnings
        assert warnings[0] in case_file.stale_risks
        assert warnings[0] in onboarding.stale_risk_warnings
    finally:
        store.close()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "README.md").write_text("# Example\n")
    (repo / "docs" / "guide.md").write_text("# Guide\n")
    _run_git(repo, "init", "-b", "main")
    _run_git(repo, "add", "README.md", "docs")
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
