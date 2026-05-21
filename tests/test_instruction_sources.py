from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from craik.contracts.models import (
    INSTRUCTION_SOURCE_DEFAULT_PATHS,
    InstructionRegistryReceipt,
    InstructionSource,
    InstructionSourceRegistration,
    InstructionSourceRegistry,
)
from craik.runtime.instructions import (
    InstructionRegistrationError,
    list_sources,
    register_source,
)
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore


def _store(tmp_path: Path) -> LocalStore:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    return store


def _source(kind: str, path: str | None = None, active: bool = True) -> InstructionSource:
    return InstructionSource(
        id=f"instruction_source_{kind}",
        project_id="project_docs",
        kind=kind,
        path=path if path is not None else INSTRUCTION_SOURCE_DEFAULT_PATHS[kind],
        owner="team:runtime",
        trust_boundary="project",
        active=active,
        declared_by="agent:orchestrator",
        created_at="2026-05-15T22:30:00Z",
    )


@pytest.mark.parametrize(
    "kind",
    [
        "agents_md",
        "claude_md",
        "gemini_md",
        "hermes_md",
        "skills_md",
        "cursor_rules",
        "github_copilot_instructions",
        "codex_instructions",
    ],
)
def test_standard_instruction_source_paths_are_supported(kind: str) -> None:
    source = _source(kind)

    assert source.path == INSTRUCTION_SOURCE_DEFAULT_PATHS[kind]
    assert source.active is True


def test_policy_doc_sources_require_declared_path() -> None:
    source = _source("policy_doc", path="docs/policies/runtime.md")

    assert source.path == "docs/policies/runtime.md"


def test_instruction_source_registration_contract_round_trips() -> None:
    registration = InstructionSourceRegistration(
        id="instruction_source_registration_agents",
        project_id="project_docs",
        source_id="instruction_source_agents_md",
        kind="agents_md",
        path="AGENTS.md",
        owner="team:runtime",
        registered_by="user:maintainer",
        registered_at="2026-05-15T22:31:00Z",
        content_hash="a" * 64,
    )
    receipt = InstructionRegistryReceipt(
        id="instruction_registry_receipt_agents",
        project_id=registration.project_id,
        source_id=registration.source_id,
        registration_id=registration.id,
        registered_by=registration.registered_by,
        target=registration.path,
        summary="Registered AGENTS.md.",
        created_at=registration.registered_at,
    )

    assert registration.path == "AGENTS.md"
    assert registration.content_hash == "a" * 64
    assert receipt.capability == "instructions.register"
    assert receipt.result_status == "passed"


def test_instruction_source_registration_rejects_bad_hash() -> None:
    with pytest.raises(ValidationError, match="content_hash"):
        InstructionSourceRegistration(
            id="instruction_source_registration_agents",
            project_id="project_docs",
            source_id="instruction_source_agents_md",
            kind="agents_md",
            path="AGENTS.md",
            owner="team:runtime",
            registered_by="user:maintainer",
            registered_at="2026-05-15T22:31:00Z",
            content_hash="not-a-sha",
        )


def test_instruction_source_registry_round_trips(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        agents = _source("agents_md")
        policy = _source("policy_doc", path="docs/policies/runtime.md")
        registry = InstructionSourceRegistry(
            id="instruction_registry_project_docs",
            project_id="project_docs",
            sources=[policy, agents],
            active_source_ids=[agents.id, policy.id],
            declared_policy_doc_paths=[policy.path],
            created_at="2026-05-15T22:31:00Z",
        )

        store.put_instruction_source(agents)
        store.put_instruction_source(policy)
        store.put_instruction_source_registry(registry)

        assert store.get_instruction_source(agents.id) == agents
        assert store.get_instruction_source_registry(registry.id) == registry
        assert store.list_instruction_sources() == [agents, policy]
        assert store.list_instruction_source_registries() == [registry]
    finally:
        store.close()


def test_standard_source_rejects_noncanonical_path() -> None:
    with pytest.raises(ValidationError, match="agents_md instruction source path"):
        _source("agents_md", path="docs/AGENTS.md")


def test_registry_rejects_inactive_active_source() -> None:
    inactive = _source("skills_md", active=False)

    with pytest.raises(ValidationError, match="inactive instruction source ids"):
        InstructionSourceRegistry(
            id="instruction_registry_project_docs",
            project_id="project_docs",
            sources=[inactive],
            active_source_ids=[inactive.id],
            created_at="2026-05-15T22:31:00Z",
        )


def test_registry_requires_policy_doc_paths_to_match_sources() -> None:
    policy = _source("policy_doc", path="docs/policies/runtime.md")

    with pytest.raises(ValidationError, match="declared policy doc paths"):
        InstructionSourceRegistry(
            id="instruction_registry_project_docs",
            project_id="project_docs",
            sources=[policy],
            active_source_ids=[policy.id],
            declared_policy_doc_paths=["docs/policies/other.md"],
            created_at="2026-05-15T22:31:00Z",
        )


def test_register_source_persists_source_registration_registry_and_receipt(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    try:
        result = register_source(
            store,
            project_id="project_docs",
            kind="agents_md",
            owner="team:runtime",
            registered_by="user:maintainer",
            source_id="instruction_source_agents_md",
            now=datetime(2026, 5, 15, 22, 31, tzinfo=UTC),
        )

        assert result.source.id == "instruction_source_agents_md"
        assert result.registration.source_id == result.source.id
        assert result.receipt.registration_id == result.registration.id
        assert store.get_instruction_source(result.source.id) == result.source
        assert store.get_instruction_source_registration(result.registration.id) == (
            result.registration
        )
        assert store.get_instruction_registry_receipt(result.receipt.id) == result.receipt
        assert store.get_instruction_source_registry(result.registry.id) == result.registry
        assert list_sources(store, project_id="project_docs") == [result.source]

        rows = store._connection.execute(  # noqa: SLF001 - verifies migration table mirror.
            "SELECT id, project_id, kind, path, registered_by FROM instruction_sources"
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            (
                "instruction_source_agents_md",
                "project_docs",
                "agents_md",
                "AGENTS.md",
                "user:maintainer",
            )
        ]
    finally:
        store.close()


def test_register_source_rejects_duplicate_source_id(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        register_source(
            store,
            project_id="project_docs",
            kind="agents_md",
            owner="team:runtime",
            registered_by="user:maintainer",
            source_id="instruction_source_agents_md",
        )

        with pytest.raises(InstructionRegistrationError, match="already registered"):
            register_source(
                store,
                project_id="project_docs",
                kind="agents_md",
                owner="team:runtime",
                registered_by="user:maintainer",
                source_id="instruction_source_agents_md",
            )
    finally:
        store.close()
