"""Tests for Claude Code grant categorization (system vs agent authority)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from craik.runtime.backend.claude_code_grants import (
    _put_claude_code_agent_grants,
    _put_claude_code_approval_receipt,
    _put_claude_code_grants,
    _put_craik_internal_grants,
)
from craik.runtime.paths import ensure_craik_home
from craik.runtime.store import LocalStore


@pytest.fixture
def store(tmp_path: Path) -> Iterator[LocalStore]:
    paths = ensure_craik_home({"CRAIK_HOME": str(tmp_path / "home")})
    store = LocalStore.from_paths(paths)
    store.initialize()
    try:
        yield store
    finally:
        store.close()


TASK_ID = "task_demo"
RECEIPT_GRANT_ID = "grant_demo_claude_receipt_write"
AGENT_GRANT_IDS = [
    "grant_demo_claude_repo_read",
    "grant_demo_claude_repo_write_docs",
    "grant_demo_claude_shell_verify",
]


def test_craik_internal_grants_are_system_authority(store: LocalStore) -> None:
    grant_ids = _put_craik_internal_grants(store, TASK_ID)

    assert RECEIPT_GRANT_ID in grant_ids
    grant = store.get_capability_grant(RECEIPT_GRANT_ID)
    assert grant is not None
    assert grant.capability == "receipt.write"
    # System authority — NOT operator-gated.
    assert grant.approved_by == "system:craik"
    assert grant.approved_by != "user:tui"


def test_agent_grants_are_provisioned_separately(store: LocalStore) -> None:
    # Default (no operator approval) is the delegate-observe path.
    grant_ids = _put_claude_code_agent_grants(store, TASK_ID)

    assert set(grant_ids) == set(AGENT_GRANT_IDS)
    for gid in AGENT_GRANT_IDS:
        grant = store.get_capability_grant(gid)
        assert grant is not None
        # Delegate-observe: no operator decided, so attribute to delegated authority.
        assert grant.approved_by == "system:craik"
    # The agent grant set must not include the craik-internal receipt grant.
    assert RECEIPT_GRANT_ID not in grant_ids
    assert "receipt.write" not in {
        store.get_capability_grant(gid).capability for gid in grant_ids
    }


def test_agent_grants_attributed_to_operator_when_approved(store: LocalStore) -> None:
    grant_ids = _put_claude_code_agent_grants(store, TASK_ID, operator_approved=True)

    assert set(grant_ids) == set(AGENT_GRANT_IDS)
    for gid in AGENT_GRANT_IDS:
        grant = store.get_capability_grant(gid)
        assert grant is not None
        # Operator genuinely approved (TUI modal-confirm path).
        assert grant.approved_by == "user:tui"


def test_agent_grants_delegate_observed_when_not_approved(store: LocalStore) -> None:
    grant_ids = _put_claude_code_agent_grants(store, TASK_ID, operator_approved=False)

    assert set(grant_ids) == set(AGENT_GRANT_IDS)
    for gid in AGENT_GRANT_IDS:
        grant = store.get_capability_grant(gid)
        assert grant is not None
        # Nobody approved write/shell; attribute honestly to delegated authority.
        assert grant.approved_by == "system:craik"
        assert grant.approved_by != "user:tui"


def test_combined_helper_provisions_both_categories(store: LocalStore) -> None:
    # Combined helper, delegate-observe default.
    grant_ids = _put_claude_code_grants(store, TASK_ID)

    # System authority present and always-on.
    assert RECEIPT_GRANT_ID in grant_ids
    receipt_grant = store.get_capability_grant(RECEIPT_GRANT_ID)
    assert receipt_grant is not None
    assert receipt_grant.approved_by == "system:craik"

    # Agent grants present and delegate-observed by default.
    for gid in AGENT_GRANT_IDS:
        grant = store.get_capability_grant(gid)
        assert grant is not None
        assert grant.approved_by == "system:craik"


def test_combined_helper_operator_approved_keeps_internal_system_authority(
    store: LocalStore,
) -> None:
    _put_claude_code_grants(store, TASK_ID, operator_approved=True)

    # craik-internal receipt.write stays system authority regardless (Task 1).
    receipt_grant = store.get_capability_grant(RECEIPT_GRANT_ID)
    assert receipt_grant is not None
    assert receipt_grant.approved_by == "system:craik"

    # Agent grants now attributed to the operator who approved.
    for gid in AGENT_GRANT_IDS:
        grant = store.get_capability_grant(gid)
        assert grant is not None
        assert grant.approved_by == "user:tui"


def test_approval_receipt_does_not_attribute_receipt_write_to_operator(
    store: LocalStore,
) -> None:
    grant_ids = _put_claude_code_grants(store, TASK_ID)

    receipt = _put_claude_code_approval_receipt(
        store, TASK_ID, grant_ids, operator_approved=True
    )

    capabilities = receipt.result.metadata["capabilities"]
    # receipt.write is system authority, not operator-approved.
    assert "receipt.write" not in capabilities
    assert "repo.read" in capabilities
    assert "repo.write.docs" in capabilities
    assert "shell.test" in capabilities
