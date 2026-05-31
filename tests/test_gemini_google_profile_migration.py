"""Active on-load migration of persisted gemini identities to google.

Task 3.2d-2: persisted ``gemini:*`` profile identities are rewritten to the
canonical ``google:*`` form on load, persisted back to disk one time, and a
legacy ``gemini:*`` id still resolves to the migrated profile.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from craik.contracts.models import CapabilityReceipt, ReceiptResult
from craik.runtime.auth.profile import AuthProfile, CredentialKind
from craik.runtime.auth.store import (
    AUTH_PROFILES_FILENAME,
    AUTH_PROFILES_SCHEMA_VERSION,
    AuthProfileStore,
)
from craik.runtime.providers.model_providers import default_model_provider_registry
from craik.runtime.providers.provider_runtime import _resolve_secret_ref_name
from craik.runtime.runners.runners import get_runner_capability_matrix


def _legacy_profile_payload(profile_id: str) -> dict[str, object]:
    """Return a persisted-shape payload for a legacy gemini profile."""
    profile = AuthProfile(
        id=profile_id,
        kind=CredentialKind.API_KEY,
        provider_family="gemini",
        metadata={"env_var": "CRAIK_GEMINI_API_KEY", "provider": "gemini"},
        created_at=datetime(2026, 5, 17, tzinfo=UTC),
        last_status="ok",
    )
    return profile.model_dump(mode="json")


def _write_legacy_store(home: Path, *profile_ids: str) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    path = home / AUTH_PROFILES_FILENAME
    payload = {
        "version": AUTH_PROFILES_SCHEMA_VERSION,
        "profiles": [_legacy_profile_payload(pid) for pid in profile_ids],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_legacy_gemini_profile_is_migrated_on_load(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_legacy_store(home, "gemini:default")
    store = AuthProfileStore(home)

    profiles = store.list()

    assert [p.id for p in profiles] == ["google:default"]
    assert profiles[0].provider_family == "google"
    assert profiles[0].metadata.get("provider") == "google"
    assert profiles[0].metadata.get("env_var") == "CRAIK_GEMINI_API_KEY"


def test_legacy_gemini_profile_is_persisted_back_to_disk(tmp_path: Path) -> None:
    home = tmp_path / "home"
    path = _write_legacy_store(home, "gemini:vertex")
    store = AuthProfileStore(home)

    store.list()

    raw = json.loads(path.read_text(encoding="utf-8"))
    ids = [item["id"] for item in raw["profiles"]]
    assert ids == ["google:vertex"]
    assert raw["profiles"][0]["provider_family"] == "google"
    assert raw["profiles"][0]["metadata"]["provider"] == "google"


def test_legacy_gemini_id_still_resolves_after_migration(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_legacy_store(home, "gemini:default")
    store = AuthProfileStore(home)

    by_legacy = store.get("gemini:default")
    by_canonical = store.get("google:default")

    assert by_legacy.id == "google:default"
    assert by_legacy == by_canonical


def test_migration_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    path = _write_legacy_store(home, "gemini:default")
    AuthProfileStore(home).list()
    first = path.read_text(encoding="utf-8")

    AuthProfileStore(home).list()
    second = path.read_text(encoding="utf-8")

    assert first == second
    assert "gemini:" not in second


def test_non_gemini_profiles_are_left_unchanged(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    path = home / AUTH_PROFILES_FILENAME
    openai = AuthProfile(
        id="openai:default",
        kind=CredentialKind.API_KEY,
        provider_family="openai",
        metadata={"env_var": "CRAIK_OPENAI_API_KEY"},
        created_at=datetime(2026, 5, 17, tzinfo=UTC),
        last_status="ok",
    )
    payload = {
        "version": AUTH_PROFILES_SCHEMA_VERSION,
        "profiles": [openai.model_dump(mode="json")],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    store = AuthProfileStore(home)

    assert [p.id for p in store.list()] == ["openai:default"]


def test_config_id_legacy_provider_gemini_resolves_to_google() -> None:
    registry = default_model_provider_registry()

    canonical = registry.require("provider_google")
    legacy = registry.require("provider_gemini")

    assert canonical.id == "provider_google"
    assert legacy is canonical


def test_runner_id_legacy_gemini_resolves_to_google_runner() -> None:
    canonical = get_runner_capability_matrix("google")
    legacy = get_runner_capability_matrix("gemini")

    assert canonical.runner.id == "google"
    assert legacy.runner.id == "google"


def test_google_model_env_canonical_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRAIK_GOOGLE_MODEL", "gemini-canonical")
    monkeypatch.setenv("CRAIK_GEMINI_MODEL", "gemini-legacy")

    resolved = _resolve_secret_ref_name(["CRAIK_GOOGLE_MODEL", "CRAIK_GEMINI_MODEL"])

    assert resolved == "CRAIK_GOOGLE_MODEL"


def test_google_model_env_legacy_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CRAIK_GOOGLE_MODEL", raising=False)
    monkeypatch.setenv("CRAIK_GEMINI_MODEL", "gemini-legacy")

    resolved = _resolve_secret_ref_name(["CRAIK_GOOGLE_MODEL", "CRAIK_GEMINI_MODEL"])

    assert resolved == "CRAIK_GEMINI_MODEL"


def test_provider_google_config_refs_are_canonical_first() -> None:
    registry = default_model_provider_registry()
    provider = registry.require("provider_google")

    assert provider.config_refs == ["CRAIK_GOOGLE_MODEL", "CRAIK_GEMINI_MODEL", *_other(provider)]


def _other(provider: object) -> list[str]:
    # Base URL canonical-first, legacy fallback follows the model refs.
    return ["CRAIK_GOOGLE_BASE_URL", "CRAIK_GEMINI_BASE_URL"]


def test_provider_gemini_stream_fixture_retains_legacy_identity() -> None:
    fixture = Path("tests/fixtures/gateway/provider_gemini_stream.jsonl")
    lines = [line for line in fixture.read_text(encoding="utf-8").splitlines() if line.strip()]
    selected = [
        json.loads(line) for line in lines if json.loads(line).get("type") == "model.selected"
    ]
    assert selected
    assert selected[0]["data"]["provider_id"] == "provider_gemini"


def test_provider_google_stream_fixture_uses_canonical_identity() -> None:
    fixture = Path("tests/fixtures/gateway/provider_google_stream.jsonl")
    assert os.path.exists(fixture)
    lines = [line for line in fixture.read_text(encoding="utf-8").splitlines() if line.strip()]
    selected = [
        json.loads(line) for line in lines if json.loads(line).get("type") == "model.selected"
    ]
    assert selected
    assert selected[0]["data"]["provider_id"] == "provider_google"


def _legacy_receipt(profile_id: str) -> CapabilityReceipt:
    """Build a valid signed authorization receipt referencing a legacy id.

    The receipt's ``target``/``auth_profile_id`` and the ``auth_profile_id``
    embedded in ``result.metadata`` all reference the pre-migration
    ``gemini:default`` id. The ``self_hash`` is computed over that historical
    payload, so the receipt is only valid while those references stay intact.
    """
    return CapabilityReceipt(
        id=f"receipt_credential_authorization_{profile_id.replace(':', '_')}_alice",
        task_id="auth_profile_authorization",
        actor="operator:admin",
        capability="credential.authorize",
        target=profile_id,
        policy_profile="strict",
        fail_open=False,
        reason="Credential profile authorization granted.",
        result=ReceiptResult(
            status="passed",
            summary="Credential profile authorization granted.",
            metadata={
                "auth_profile_id": profile_id,
                "authorized_operator": "alice",
                "authorized_operator_group": None,
            },
        ),
        auth_profile_id=profile_id,
        redacted=True,
        created_at=datetime(2026, 5, 17, tzinfo=UTC),
    )


def _write_legacy_store_with_receipt(home: Path, profile_id: str) -> tuple[Path, str]:
    """Persist a legacy gemini profile carrying a signed provenance receipt."""
    home.mkdir(parents=True, exist_ok=True)
    path = home / AUTH_PROFILES_FILENAME
    receipt = _legacy_receipt(profile_id)
    profile = AuthProfile(
        id=profile_id,
        kind=CredentialKind.API_KEY,
        provider_family="gemini",
        metadata={"env_var": "CRAIK_GEMINI_API_KEY", "provider": "gemini"},
        created_at=datetime(2026, 5, 17, tzinfo=UTC),
        last_status="ok",
        authorization_provenance=[receipt],
    )
    payload = {
        "version": AUTH_PROFILES_SCHEMA_VERSION,
        "profiles": [profile.model_dump(mode="json")],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path, receipt.self_hash


def test_migration_preserves_signed_provenance_receipts(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _path, original_hash = _write_legacy_store_with_receipt(home, "gemini:default")
    assert original_hash  # the receipt was signed before migration

    profile = AuthProfileStore(home).get("gemini:default")

    # (a) profile identity migrated to the canonical google form.
    assert profile.id == "google:default"
    assert profile.provider_family == "google"

    # (b) provenance receipt is byte-for-byte unchanged: identical self_hash and
    # the intentional hash-preserving historical references still read gemini.
    assert len(profile.authorization_provenance) == 1
    receipt = profile.authorization_provenance[0]
    assert receipt.self_hash == original_hash
    assert receipt.target == "gemini:default"
    assert receipt.auth_profile_id == "gemini:default"
    assert receipt.result.metadata["auth_profile_id"] == "gemini:default"

    # (c) re-loading/re-validating the migrated profile does not raise; the
    # receipt-hash validation (CapabilityReceipt.validate_receipt_hash) still
    # passes because the signed payload is intact.
    reloaded = AuthProfileStore(home).get("google:default")
    revalidated = reloaded.authorization_provenance[0].validate_receipt_hash()
    assert revalidated.self_hash == original_hash
