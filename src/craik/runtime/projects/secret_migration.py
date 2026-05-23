"""Secret migration policy for import workflows."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from pydantic import Field, model_validator

from craik.contracts.models import CraikModel
from craik.runtime.shell.credential_storage import CredentialStorageStatus

SecretMigrationHandling = Literal["redact", "reference", "reconfigure", "block"]
SecretMigrationDecisionStatus = Literal[
    "allowed",
    "redacted",
    "referenced",
    "operator_reconfiguration_required",
    "blocked",
]
SECRET_FIELD_MARKERS = ("secret", "token", "password", "api_key", "apikey", "credential")


class SecretMigrationPolicyRule(CraikModel):
    """Policy for one source field that may contain secret material."""

    source_field: str
    handling: SecretMigrationHandling
    reason: str
    dry_run_warning: str
    requires_operator_action: bool = False
    receipt_required: bool = True

    @model_validator(mode="after")
    def validate_rule(self) -> SecretMigrationPolicyRule:
        """Keep secret handling auditable."""
        if self.handling in {"reconfigure", "block"} and not self.requires_operator_action:
            raise ValueError("reconfigure and block secret rules require operator action")
        if self.handling != "redact" and not self.receipt_required:
            raise ValueError("non-redaction secret rules require receipts")
        if not self.reason:
            raise ValueError("secret migration rules require reason")
        if not self.dry_run_warning:
            raise ValueError("secret migration rules require dry_run_warning")
        return self


class SecretMigrationPolicy(CraikModel):
    """Policy describing how migration handles source secrets."""

    id: str
    source_name: str
    rules: list[SecretMigrationPolicyRule] = Field(min_length=1)
    default_secret_handling: Literal["block"] = "block"
    prohibited_behavior: str = "copy_secret_value"
    policy_envelope_id: str
    evidence_ids: list[str] = Field(min_length=1)
    receipt_ids: list[str] = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_policy(self) -> SecretMigrationPolicy:
        """Ensure the policy cannot authorize secret copying."""
        if self.prohibited_behavior != "copy_secret_value":
            raise ValueError("secret migration policy must prohibit secret value copying")
        if self.default_secret_handling != "block":
            raise ValueError("unknown secret fields must be blocked by default")
        if not self.policy_envelope_id:
            raise ValueError("secret migration policies require policy_envelope_id")
        return self


class SecretMigrationDecision(CraikModel):
    """Decision produced for one import field under a secret migration policy."""

    source_field: str
    status: SecretMigrationDecisionStatus
    warning: str | None = None
    reason: str | None = None
    policy_id: str
    policy_envelope_id: str
    evidence_ids: list[str] = Field(min_length=1)
    receipt_ids: list[str] = Field(default_factory=list)
    contains_secret: bool
    copied_secret_value: Literal[False] = False
    requires_operator_action: bool = False

    @model_validator(mode="after")
    def validate_decision(self) -> SecretMigrationDecision:
        """Require receipts for every secret migration decision."""
        if self.contains_secret and not self.receipt_ids:
            raise ValueError("secret migration decisions require receipts")
        if self.status == "allowed" and self.contains_secret:
            raise ValueError("secret fields cannot be allowed without safe handling")
        if self.status in {"operator_reconfiguration_required", "blocked"}:
            if not self.requires_operator_action:
                raise ValueError("blocked and reconfiguration decisions require operator action")
        return self


class SecretInventoryItem(CraikModel):
    """One redacted secret-like field discovered in source state."""

    source_id: str
    field_path: str
    value_fingerprint: str
    value_length: int
    handling: SecretMigrationDecisionStatus = "blocked"

    @model_validator(mode="after")
    def validate_inventory_item(self) -> SecretInventoryItem:
        """Ensure inventory entries do not carry secret values."""
        if not self.source_id:
            raise ValueError("secret inventory items require source_id")
        if not self.field_path:
            raise ValueError("secret inventory items require field_path")
        if len(self.value_fingerprint) != 16:
            raise ValueError("secret inventory fingerprints must be truncated hashes")
        return self


class SecretMigrationReceipt(CraikModel):
    """Receipt for an optional keyring secret migration action."""

    id: str
    source_id: str
    field_path: str
    target_ref: str
    backend: str
    status: Literal["dry_run", "imported", "blocked"]
    copied_secret_value: Literal[False] = False
    operator_confirmed: bool = False
    value_fingerprint: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_receipt(self) -> SecretMigrationReceipt:
        """Keep receipts redacted and confirmation-bound."""
        if self.status == "imported" and not self.operator_confirmed:
            raise ValueError("imported secret migrations require operator confirmation")
        if any(marker in self.target_ref.lower() for marker in ("sk-", "password=", "token=")):
            raise ValueError("secret migration target_ref must not contain secret material")
        return self


class SecretKeyringWriter(Protocol):
    """Minimal keyring writer used by secret migration."""

    def set_secret(self, target_ref: str, value: str) -> None:
        """Write one secret value to the target keyring reference."""
        raise NotImplementedError


class InMemorySecretKeyring:
    """Test keyring backend for secret migration flows."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set_secret(self, target_ref: str, value: str) -> None:
        self.values[target_ref] = value


def detect_secret_inventory(
    payload: Any,
    *,
    source_id: str,
) -> list[SecretInventoryItem]:
    """Return a redacted inventory of secret-like source fields."""
    return [
        SecretInventoryItem(
            source_id=source_id,
            field_path=field_path,
            value_fingerprint=_fingerprint(str(value)),
            value_length=len(str(value)),
            handling="blocked",
        )
        for field_path, value in sorted(_secret_values(payload))
    ]


def migrate_secret_inventory_to_keyring(
    payload: Any,
    *,
    source_id: str,
    keyring: SecretKeyringWriter,
    backend: CredentialStorageStatus,
    confirm: bool,
    target_prefix: str = "craik/migration",
) -> list[SecretMigrationReceipt]:
    """Optionally write detected source secrets into a keyring backend."""
    receipts: list[SecretMigrationReceipt] = []
    for item in detect_secret_inventory(payload, source_id=source_id):
        target_ref = f"{target_prefix}/{_safe_ref(source_id)}/{_safe_ref(item.field_path)}"
        if not confirm:
            receipts.append(
                _receipt(
                    item,
                    target_ref=target_ref,
                    backend=backend.backend,
                    status="dry_run",
                    operator_confirmed=False,
                )
            )
            continue
        if not backend.secure:
            receipts.append(
                _receipt(
                    item,
                    target_ref=target_ref,
                    backend=backend.backend,
                    status="blocked",
                    operator_confirmed=True,
                )
            )
            continue
        value = _value_at_path(payload, item.field_path)
        keyring.set_secret(target_ref, str(value))
        receipts.append(
            _receipt(
                item,
                target_ref=target_ref,
                backend=backend.backend,
                status="imported",
                operator_confirmed=True,
            )
        )
    return receipts


def evaluate_secret_migration(
    *,
    source_field: str,
    contains_secret: bool,
    policy: SecretMigrationPolicy,
) -> SecretMigrationDecision:
    """Evaluate a source field under a secret migration policy."""
    if not contains_secret:
        return SecretMigrationDecision(
            source_field=source_field,
            status="allowed",
            policy_id=policy.id,
            policy_envelope_id=policy.policy_envelope_id,
            evidence_ids=policy.evidence_ids,
            contains_secret=False,
        )

    rule = next((item for item in policy.rules if item.source_field == source_field), None)
    if rule is None:
        return SecretMigrationDecision(
            source_field=source_field,
            status="blocked",
            warning="secret field has no migration policy rule",
            reason="unknown secret fields are blocked by default",
            policy_id=policy.id,
            policy_envelope_id=policy.policy_envelope_id,
            evidence_ids=policy.evidence_ids,
            receipt_ids=policy.receipt_ids,
            contains_secret=True,
            requires_operator_action=True,
        )

    return SecretMigrationDecision(
        source_field=source_field,
        status=_decision_status(rule.handling),
        warning=rule.dry_run_warning,
        reason=rule.reason,
        policy_id=policy.id,
        policy_envelope_id=policy.policy_envelope_id,
        evidence_ids=policy.evidence_ids,
        receipt_ids=policy.receipt_ids if rule.receipt_required else [],
        contains_secret=True,
        requires_operator_action=rule.requires_operator_action,
    )


def _decision_status(handling: SecretMigrationHandling) -> SecretMigrationDecisionStatus:
    if handling == "redact":
        return "redacted"
    if handling == "reference":
        return "referenced"
    if handling == "reconfigure":
        return "operator_reconfiguration_required"
    return "blocked"


def _secret_values(payload: Any, prefix: str = "") -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            field = f"{prefix}.{key}" if prefix else str(key)
            if _is_secret_field(str(key)) and isinstance(value, str) and value:
                values.append((field, value))
                continue
            values.extend(_secret_values(value, field))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            values.extend(_secret_values(value, f"{prefix}[{index}]"))
    return values


def _is_secret_field(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SECRET_FIELD_MARKERS)


def _value_at_path(payload: Any, path: str) -> Any:
    current = payload
    for segment in path.replace("]", "").split("."):
        if "[" in segment:
            key, index = segment.split("[", 1)
            if key:
                current = current[key]
            current = current[int(index)]
        else:
            current = current[segment]
    return current


def _receipt(
    item: SecretInventoryItem,
    *,
    target_ref: str,
    backend: str,
    status: Literal["dry_run", "imported", "blocked"],
    operator_confirmed: bool,
) -> SecretMigrationReceipt:
    return SecretMigrationReceipt(
        id=f"secret_migration_{_safe_ref(item.source_id)}_{_safe_ref(item.field_path)}",
        source_id=item.source_id,
        field_path=item.field_path,
        target_ref=target_ref,
        backend=backend,
        status=status,
        operator_confirmed=operator_confirmed,
        value_fingerprint=item.value_fingerprint,
    )


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _safe_ref(value: str) -> str:
    normalized = "".join(character if character.isalnum() else "-" for character in value.lower())
    return "-".join(part for part in normalized.split("-") if part) or "secret"
