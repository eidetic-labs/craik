import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from craik.contracts.models import DistilledInstructionProposal
from craik.runtime.instruction_distillation import (
    categorize_instruction,
    ingest_project_instructions,
)
from craik.runtime.instructions import register_source
from craik.runtime.paths import ensure_craik_home
from craik.runtime.projects.instruction_ingestion import InstructionStatement
from craik.runtime.projects.instruction_sources import (
    render_distilled_instruction_json,
    render_distilled_instruction_markdown,
)
from craik.runtime.projects.project_registry import ProjectRegistry
from craik.runtime.store import LocalStore

REQUIRED_CATEGORIES = [
    "instruction",
    "policy",
    "preference",
    "command",
    "boundary",
    "handoff_rule",
    "memory_rule",
    "security_rule",
    "stale_risk",
]


def _store(tmp_path: Path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    return store


def _proposal(category: str, evidence_ids: list[str] | None = None) -> DistilledInstructionProposal:
    return DistilledInstructionProposal(
        id=f"distilled_instruction_{category}",
        project_id="project_docs",
        task_id="task_distill",
        source_id="instruction_source_agents_md",
        snapshot_id="instruction_snapshot_agents_md",
        category=category,
        statement=f"Fixture {category} statement.",
        rationale=f"Fixture {category} rationale.",
        confidence=0.82,
        provenance_ids=["instruction_provenance_agents_rule"],
        evidence_ids=evidence_ids if evidence_ids is not None else ["evidence_agents_md"],
        created_at="2026-05-15T22:30:00Z",
    )


@pytest.mark.parametrize(
    ("text", "category", "matched_rule", "source_kind"),
    [
        ("Always ensure tests pass.", "instruction", "imperative_keyword", None),
        (
            "Policy authority applies to this repository.",
            "policy",
            "policy_doc_source",
            "policy_doc",
        ),
        ("Prefer concise release notes.", "preference", "preference_keyword", None),
        ("Run pytest before release.", "command", "command_keyword", None),
        ("Never push directly to main.", "boundary", "boundary_keyword", None),
        ("Write a handoff before delegation.", "handoff_rule", "handoff_keyword", None),
        ("Remember durable facts in memory.", "memory_rule", "memory_keyword", None),
        ("Redact every credential token.", "security_rule", "security_keyword", None),
        ("Last updated in 2024; verify freshness.", "stale_risk", "stale_risk_keyword", None),
    ],
)
def test_categorizer_covers_required_categories(
    text: str,
    category: str,
    matched_rule: str,
    source_kind: str | None,
) -> None:
    result = categorize_instruction(_statement(text), source_kind=source_kind)

    assert result.category == category
    assert result.confidence == 0.6
    assert result.matched_rule == matched_rule


def test_categorizer_surfaces_unclassified_candidates() -> None:
    result = categorize_instruction(_statement("Blue sky."))

    assert result.category is None
    assert result.confidence == 0.0
    assert result.matched_rule == "unclassified"


@pytest.mark.parametrize("category", REQUIRED_CATEGORIES)
def test_distilled_instruction_proposal_supports_required_categories(category: str) -> None:
    proposal = _proposal(category)

    assert proposal.category == category
    assert proposal.promotion_status == "proposed"
    assert proposal.provenance_ids == ["instruction_provenance_agents_rule"]


def test_distilled_instruction_proposal_round_trips_and_renders(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        proposal = _proposal("boundary")

        store.put_distilled_instruction_proposal(proposal)

        assert store.get_distilled_instruction_proposal(proposal.id) == proposal
        assert store.list_distilled_instruction_proposals() == [proposal]
        markdown = render_distilled_instruction_markdown(proposal)
        assert "- Category: boundary" in markdown
        assert "instruction_provenance_agents_rule" in markdown
        assert render_distilled_instruction_json(proposal) == render_distilled_instruction_json(
            DistilledInstructionProposal.model_validate_json(
                render_distilled_instruction_json(proposal)
            )
        )
    finally:
        store.close()


def test_ingest_project_instructions_writes_categorized_proposals(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        repo = _repo(tmp_path)
        project = ProjectRegistry(store).add_project(repo, name="Docs")
        (repo / "AGENTS.md").write_text(
            "- Always ensure tests pass.\n- Run pytest before release.\n",
            encoding="utf-8",
        )
        (repo / ".cursorrules").write_text(
            "Never push directly to main.\nRemember durable facts in memory.\n",
            encoding="utf-8",
        )
        (repo / "docs" / "runtime-policy.md").write_text(
            "Policy authority applies to this repository.\n",
            encoding="utf-8",
        )
        register_source(
            store,
            project_id=project.id,
            kind="agents_md",
            owner="team:runtime",
            registered_by="agent:test",
        )
        register_source(
            store,
            project_id=project.id,
            kind="cursor_rules",
            owner="team:runtime",
            registered_by="agent:test",
        )
        register_source(
            store,
            project_id=project.id,
            kind="policy_doc",
            path="docs/runtime-policy.md",
            owner="team:runtime",
            registered_by="agent:test",
        )

        summary = ingest_project_instructions(
            store,
            project.id,
            now=datetime(2026, 5, 21, 4, 30, tzinfo=UTC),
        )

        proposals = sorted(
            store.list_distilled_instruction_proposals(),
            key=lambda proposal: proposal.statement,
        )
        assert summary.source_count == 3
        assert summary.snapshot_count == 3
        assert summary.provenance_count == 5
        assert summary.proposal_count == 5
        assert summary.unclassified_count == 0
        assert summary.warnings == []
        assert {proposal.category for proposal in proposals} == {
            "boundary",
            "command",
            "instruction",
            "memory_rule",
            "policy",
        }
        assert all(proposal.snapshot_id for proposal in proposals)
        assert all(proposal.provenance_ids for proposal in proposals)
        assert all(proposal.evidence_ids == proposal.provenance_ids for proposal in proposals)
        assert store.list_instruction_provenance()
        assert store.list_instruction_source_snapshots()
    finally:
        store.close()


def test_ingest_project_instructions_reports_unclassified_candidates(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    try:
        repo = _repo(tmp_path)
        project = ProjectRegistry(store).add_project(repo, name="Docs")
        (repo / "AGENTS.md").write_text("- Blue sky.\n", encoding="utf-8")
        register_source(
            store,
            project_id=project.id,
            kind="agents_md",
            owner="team:runtime",
            registered_by="agent:test",
        )

        summary = ingest_project_instructions(store, project.id)

        assert summary.proposal_count == 0
        assert summary.unclassified_count == 1
        assert len(summary.warnings) == 1
        assert "Unclassified instruction candidate" in summary.warnings[0]
        assert store.list_distilled_instruction_proposals() == []
    finally:
        store.close()


def test_distilled_instruction_proposals_require_provenance() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        DistilledInstructionProposal(
            id="distilled_instruction_missing_provenance",
            project_id="project_docs",
            source_id="instruction_source_agents_md",
            category="instruction",
            statement="Missing provenance.",
            rationale="No provenance should fail validation.",
            confidence=0.5,
            provenance_ids=[],
            created_at="2026-05-15T22:30:00Z",
        )


def _statement(text: str) -> InstructionStatement:
    return InstructionStatement(
        text=text,
        start_line=1,
        end_line=1,
        start_column=1,
        end_column=max(len(text), 1),
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "README.md").write_text("# Example\n", encoding="utf-8")
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


def test_policy_and_security_rule_distillations_require_evidence() -> None:
    with pytest.raises(ValidationError, match="require evidence ids"):
        _proposal("policy", evidence_ids=[])
    with pytest.raises(ValidationError, match="require evidence ids"):
        _proposal("security_rule", evidence_ids=[])


def test_approved_distillation_requires_review_metadata() -> None:
    with pytest.raises(ValidationError, match="promoted_constraint_id"):
        DistilledInstructionProposal(
            id="distilled_instruction_approved_without_constraint",
            project_id="project_docs",
            source_id="instruction_source_agents_md",
            category="instruction",
            statement="Approved instruction.",
            rationale="Needs promoted constraint.",
            confidence=0.9,
            provenance_ids=["instruction_provenance_agents_rule"],
            promotion_status="approved",
            decided_by="user:maintainer",
            decided_at="2026-05-15T22:31:00Z",
            created_at="2026-05-15T22:30:00Z",
        )

    with pytest.raises(ValidationError, match="reviewer and decision time"):
        DistilledInstructionProposal(
            id="distilled_instruction_approved",
            project_id="project_docs",
            source_id="instruction_source_agents_md",
            category="instruction",
            statement="Approved instruction.",
            rationale="Needs review metadata.",
            confidence=0.9,
            provenance_ids=["instruction_provenance_agents_rule"],
            promotion_status="approved",
            promoted_constraint_id="constraint_agents_rule",
            created_at="2026-05-15T22:30:00Z",
        )
