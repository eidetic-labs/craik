import os
import stat
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from craik.runtime.auth import (
    AuthProfile,
    AuthProfileNotFoundError,
    AuthProfileStore,
    CredentialKind,
)
from craik.runtime.auth.store import AUTH_PROFILES_FILENAME
from craik.runtime.providers.provider_transport import ProviderFamily


def _profile(profile_id: str, *, env_var: str = "OPENAI_API_KEY") -> AuthProfile:
    family = profile_id.split(":", 1)[0]
    return AuthProfile(
        id=profile_id,
        kind=CredentialKind.API_KEY,
        provider_family=cast(ProviderFamily, family),
        metadata={"env_var": env_var},
        created_at=datetime(2026, 5, 17, tzinfo=UTC),
        last_status="unknown",
    )


def test_auth_profile_store_round_trip_preserves_fields(tmp_path: Path) -> None:
    store = AuthProfileStore(tmp_path)
    profile = _profile("openai:work")

    store.put(profile)
    restored = store.get("openai:work")

    assert restored == profile
    assert store.list() == [profile]


def test_auth_profile_store_delete_and_missing_get(tmp_path: Path) -> None:
    store = AuthProfileStore(tmp_path)
    store.put(_profile("anthropic:work", env_var="ANTHROPIC_API_KEY"))

    store.delete("anthropic:work")

    assert store.list() == []
    with pytest.raises(AuthProfileNotFoundError):
        store.get("anthropic:work")


def test_auth_profile_store_mark_used_updates_status_and_timestamp(tmp_path: Path) -> None:
    store = AuthProfileStore(tmp_path)
    store.put(_profile("openai:work"))

    updated = store.mark_used("openai:work", "ok")

    assert updated.last_status == "ok"
    assert updated.last_used_at is not None
    assert store.get("openai:work").last_status == "ok"


def test_auth_profile_store_approve_records_marker(tmp_path: Path) -> None:
    store = AuthProfileStore(tmp_path)
    store.put(_profile("openai:work"))

    updated = store.approve(
        "openai:work",
        run_id="run_approval",
        approved_by="operator:local",
        approved_at=datetime(2026, 5, 17, 12, 0, tzinfo=UTC),
    )

    assert updated.metadata["approval"] == {
        "run_id": "run_approval",
        "approved_by": "operator:local",
        "approved_at": "2026-05-17T12:00:00+00:00",
    }


def test_auth_profile_store_grant_authorization_records_receipt(tmp_path: Path) -> None:
    store = AuthProfileStore(tmp_path)
    store.put(_profile("openai:work"))

    updated = store.grant_authorization(
        "openai:work",
        to_subject="operator-123",
        to_group="prod-deploy",
        granted_by="operator:admin",
        granted_at=datetime(2026, 5, 17, 12, 0, tzinfo=UTC),
    )

    assert updated.authorized_operators == ["operator-123"]
    assert updated.authorized_operator_groups == ["prod-deploy"]
    assert updated.authorization_provenance[0].capability == "credential.authorize"
    assert updated.authorization_provenance[0].actor == "operator:admin"
    assert store.get("openai:work").authorization_provenance[0].target == "openai:work"


@pytest.mark.parametrize(
    "field",
    ["authorized_operators", "authorized_operator_groups"],
)
def test_auth_profile_rejects_empty_authorization_scopes(field: str) -> None:
    kwargs: dict[str, Any] = {field: []}

    with pytest.raises(ValidationError, match="authorization scope must be None"):
        AuthProfile(
            id="openai:work",
            kind=CredentialKind.API_KEY,
            provider_family=cast(ProviderFamily, "openai"),
            metadata={"env_var": "OPENAI_API_KEY"},
            created_at=datetime(2026, 5, 17, tzinfo=UTC),
            **kwargs,
        )


def test_auth_profile_store_writes_owner_only_file_on_posix(tmp_path: Path) -> None:
    store = AuthProfileStore(tmp_path)

    store.put(_profile("openai:work"))

    if os.name != "posix":
        return
    mode = stat.S_IMODE((tmp_path / AUTH_PROFILES_FILENAME).stat().st_mode)
    assert mode == 0o600


def test_auth_profile_store_concurrent_writes_do_not_corrupt_file(tmp_path: Path) -> None:
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def write_profile(profile_id: str) -> None:
        try:
            store = AuthProfileStore(tmp_path)
            barrier.wait(timeout=5)
            store.put(_profile(profile_id))
        except Exception as exc:  # pragma: no cover - assertion reports thread errors
            errors.append(exc)

    threads = [
        threading.Thread(target=write_profile, args=("openai:work",)),
        threading.Thread(target=write_profile, args=("anthropic:work",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert errors == []
    profiles = AuthProfileStore(tmp_path).list()
    assert [profile.id for profile in profiles] == ["anthropic:work", "openai:work"]
