import pytest
from pydantic import ValidationError

from craik.runtime.projects.secret_migration import (
    InMemorySecretKeyring,
    SecretMigrationDecision,
    SecretMigrationPolicy,
    SecretMigrationPolicyRule,
    detect_secret_inventory,
    evaluate_secret_migration,
    migrate_secret_inventory_to_keyring,
)
from craik.runtime.shell.credential_storage import CredentialStorageStatus


def test_secret_migration_policy_requires_operator_reconfiguration() -> None:
    policy = _policy(
        rules=[
            SecretMigrationPolicyRule(
                source_field="api_token",
                handling="reconfigure",
                reason="Tokens must be created by the operator in the target runtime.",
                dry_run_warning="api_token will not be copied during migration.",
                requires_operator_action=True,
            )
        ]
    )

    decision = evaluate_secret_migration(
        source_field="api_token",
        contains_secret=True,
        policy=policy,
    )

    assert decision.status == "operator_reconfiguration_required"
    assert decision.copied_secret_value is False
    assert decision.requires_operator_action is True
    assert decision.warning == "api_token will not be copied during migration."
    assert decision.policy_envelope_id == "policy_migration"
    assert decision.evidence_ids == ["evidence_secret_policy"]
    assert decision.receipt_ids == ["receipt_secret_migration"]


def test_secret_migration_policy_supports_redaction_and_reference_only_metadata() -> None:
    policy = _policy(
        rules=[
            SecretMigrationPolicyRule(
                source_field="inline_secret",
                handling="redact",
                reason="Inline secret values are replaced with redaction markers.",
                dry_run_warning="inline_secret will be redacted.",
            ),
            SecretMigrationPolicyRule(
                source_field="vault_ref",
                handling="reference",
                reason="Reference identifiers are portable without copying secret bytes.",
                dry_run_warning="vault_ref will keep a reference only.",
            ),
        ]
    )

    redacted = evaluate_secret_migration(
        source_field="inline_secret",
        contains_secret=True,
        policy=policy,
    )
    referenced = evaluate_secret_migration(
        source_field="vault_ref",
        contains_secret=True,
        policy=policy,
    )

    assert redacted.status == "redacted"
    assert referenced.status == "referenced"
    assert redacted.copied_secret_value is False
    assert referenced.copied_secret_value is False


def test_secret_migration_policy_blocks_unknown_secret_fields_by_default() -> None:
    decision = evaluate_secret_migration(
        source_field="unmapped_secret",
        contains_secret=True,
        policy=_policy(),
    )

    assert decision.status == "blocked"
    assert decision.requires_operator_action is True
    assert decision.warning == "secret field has no migration policy rule"
    assert decision.copied_secret_value is False


def test_secret_migration_policy_allows_non_secret_fields_without_receipts() -> None:
    decision = evaluate_secret_migration(
        source_field="display_name",
        contains_secret=False,
        policy=_policy(),
    )

    assert decision.status == "allowed"
    assert decision.receipt_ids == []
    assert decision.copied_secret_value is False


def test_secret_migration_policy_validates_policy_envelope_and_copy_prohibition() -> None:
    with pytest.raises(ValidationError, match="prohibit secret value copying"):
        _policy(prohibited_behavior="copy_with_redaction")

    with pytest.raises(ValidationError, match="default_secret_handling"):
        _policy(default_secret_handling="redact")

    with pytest.raises(ValidationError, match="policy_envelope_id"):
        _policy(policy_envelope_id="")

    with pytest.raises(ValidationError):
        _policy(evidence_ids=[])


def test_secret_migration_rules_require_warnings_receipts_and_operator_actions() -> None:
    with pytest.raises(ValidationError, match="operator action"):
        SecretMigrationPolicyRule(
            source_field="api_token",
            handling="reconfigure",
            reason="Needs target runtime setup.",
            dry_run_warning="api_token will not be copied.",
        )

    with pytest.raises(ValidationError, match="receipts"):
        SecretMigrationPolicyRule(
            source_field="vault_ref",
            handling="reference",
            reason="Only reference metadata may migrate.",
            dry_run_warning="vault_ref will keep a reference only.",
            receipt_required=False,
        )

    with pytest.raises(ValidationError, match="dry_run_warning"):
        SecretMigrationPolicyRule(
            source_field="inline_secret",
            handling="redact",
            reason="Inline secret values are redacted.",
            dry_run_warning="",
        )


def test_secret_migration_decisions_reject_secret_allow_and_missing_receipts() -> None:
    with pytest.raises(ValidationError, match="cannot be allowed"):
        SecretMigrationDecision(
            source_field="api_token",
            status="allowed",
            policy_id="secret_policy",
            policy_envelope_id="policy_migration",
            evidence_ids=["evidence_secret_policy"],
            receipt_ids=["receipt_secret_migration"],
            contains_secret=True,
        )


def test_secret_inventory_detects_secret_fields_without_values() -> None:
    payload = {
        "provider": {
            "api_key": "sk_live_should_not_escape",
            "nested": {"password": "also-hidden"},
        }
    }

    inventory = detect_secret_inventory(payload, source_id="provider_openai")
    dumped = [item.model_dump(mode="json") for item in inventory]

    assert [item.field_path for item in inventory] == [
        "provider.api_key",
        "provider.nested.password",
    ]
    assert inventory[0].value_length == len("sk_live_should_not_escape")
    assert "sk_live_should_not_escape" not in str(dumped)
    assert "also-hidden" not in str(dumped)


def test_secret_migration_keyring_import_requires_confirmation() -> None:
    payload = {"api_key": "sk_live_should_not_escape"}
    keyring = InMemorySecretKeyring()
    backend = CredentialStorageStatus(
        backend="test-keyring",
        status="available",
        secure=True,
    )

    receipts = migrate_secret_inventory_to_keyring(
        payload,
        source_id="provider_openai",
        keyring=keyring,
        backend=backend,
        confirm=False,
    )

    assert receipts[0].status == "dry_run"
    assert receipts[0].copied_secret_value is False
    assert keyring.values == {}

    applied = migrate_secret_inventory_to_keyring(
        payload,
        source_id="provider_openai",
        keyring=keyring,
        backend=backend,
        confirm=True,
    )

    assert applied[0].status == "imported"
    assert applied[0].operator_confirmed is True
    assert keyring.values[applied[0].target_ref] == "sk_live_should_not_escape"
    assert "sk_live_should_not_escape" not in str(applied[0].model_dump(mode="json"))


def test_secret_migration_blocks_file_fallback_keyring_import() -> None:
    payload = {"api_key": "sk_live_should_not_escape"}
    keyring = InMemorySecretKeyring()
    backend = CredentialStorageStatus(
        backend="file",
        status="fallback",
        secure=False,
        warning="plaintext at rest",
    )

    receipts = migrate_secret_inventory_to_keyring(
        payload,
        source_id="provider_openai",
        keyring=keyring,
        backend=backend,
        confirm=True,
    )

    assert receipts[0].status == "blocked"
    assert receipts[0].backend == "file"
    assert keyring.values == {}

    with pytest.raises(ValidationError, match="require receipts"):
        SecretMigrationDecision(
            source_field="api_token",
            status="redacted",
            policy_id="secret_policy",
            policy_envelope_id="policy_migration",
            evidence_ids=["evidence_secret_policy"],
            contains_secret=True,
        )


def _policy(**overrides: object) -> SecretMigrationPolicy:
    payload = {
        "id": "secret_policy",
        "source_name": "Adjacent Tool",
        "rules": [
            SecretMigrationPolicyRule(
                source_field="password",
                handling="redact",
                reason="Passwords are never imported from source records.",
                dry_run_warning="password will be redacted.",
            )
        ],
        "policy_envelope_id": "policy_migration",
        "evidence_ids": ["evidence_secret_policy"],
        "receipt_ids": ["receipt_secret_migration"],
    }
    payload.update(overrides)
    return SecretMigrationPolicy.model_validate(payload)
