import pytest
from pydantic import ValidationError

from craik.runtime.projects.migration_maps import (
    DEFAULT_OBJECT_TYPE_MAPS,
    MigrationFieldMap,
    MigrationMap,
    MigrationObjectMap,
    migration_map_for_object,
    migration_plan_map,
)


def test_migration_map_records_memory_field_mappings() -> None:
    migration_map = MigrationMap(
        id="migration_map_memory",
        surface="memory",
        source_name="Adjacent Memory Store",
        field_maps=[
            MigrationFieldMap(
                source_field="subject",
                target_field="entity",
                support="supported",
                transform_notes="Use source subject as fact entity.",
            ),
            MigrationFieldMap(
                source_field="secret_value",
                target_field=None,
                support="unsupported",
                transform_notes="Secrets are reconfigured, not imported.",
                unsupported_reason="secret material is not portable",
            ),
        ],
        compatibility_notes=["Confidence defaults need operator review."],
        policy_envelope_id="policy_migration",
        evidence_ids=["evidence_map"],
        receipt_ids=["receipt_map"],
    )

    assert migration_map.surface == "memory"
    assert migration_map.field_maps[0].target_field == "entity"
    assert migration_map.field_maps[1].unsupported_reason == "secret material is not portable"
    assert migration_map.compatibility_notes == ["Confidence defaults need operator review."]


def test_migration_map_covers_skill_and_config_surfaces() -> None:
    for surface in ("skill", "config", "agent", "model", "channel", "session"):
        migration_map = MigrationMap(
            id=f"migration_map_{surface}",
            surface=surface,
            source_name="Adjacent Tool",
            field_maps=[
                MigrationFieldMap(
                    source_field="name",
                    target_field="id",
                    support="supported",
                    transform_notes="Normalize source name to stable id.",
                )
            ],
            policy_envelope_id="policy_migration",
            evidence_ids=["evidence_map"],
            receipt_ids=["receipt_map"],
        )

        assert migration_map.surface == surface


def test_default_object_maps_cover_v0_12_required_surfaces() -> None:
    covered = {item.source_type for item in DEFAULT_OBJECT_TYPE_MAPS}

    assert covered >= {
        "agent",
        "approval",
        "channel",
        "fallback",
        "gateway",
        "memory",
        "model",
        "profile",
        "sandbox",
        "schedule",
        "session",
        "skill",
    }


def test_migration_map_for_object_assigns_status_and_target() -> None:
    agent = migration_map_for_object(source_id="agents.json:reviewer", source_type="agent")
    model = migration_map_for_object(source_id="models.json:primary", source_type="provider")
    persona = migration_map_for_object(source_id="personas.json:writer", source_type="persona")

    assert agent.status == "importable"
    assert agent.target_schema == "craik.agent_profile"
    assert agent.target_id
    assert model.status == "partial"
    assert model.target_schema == "craik.model_provider"
    assert persona.status == "importable"
    assert persona.target_schema == "craik.profile"


def test_migration_map_for_object_skips_secret_bearing_records() -> None:
    mapped = migration_map_for_object(
        source_id="providers.json:openai",
        source_type="model",
        secret_fields=["api_key"],
    )

    assert mapped.status == "skipped-secret"
    assert mapped.target_id is None
    assert mapped.secret_fields == ["api_key"]
    assert "raw secret" in mapped.warnings[0]


def test_migration_map_for_object_marks_unknown_shapes_unsupported() -> None:
    mapped = migration_map_for_object(source_id="unknown.json:item", source_type="widget")

    assert mapped.status == "unsupported"
    assert mapped.target_schema == "manual.review"
    assert mapped.required_actions == ["review source object manually"]
    assert mapped.unsupported_reason == "no Craik migration target is defined for widget"


def test_migration_plan_map_counts_statuses() -> None:
    plan = migration_plan_map(
        plan_id="migration_plan_map_fixture",
        source_name="fixture",
        objects=[
            migration_map_for_object(source_id="agents.json:reviewer", source_type="agent"),
            migration_map_for_object(source_id="models.json:primary", source_type="model"),
            migration_map_for_object(
                source_id="providers.json:openai",
                source_type="model",
                secret_fields=["api_key"],
            ),
            migration_map_for_object(source_id="unknown.json:item", source_type="widget"),
        ],
    )

    assert plan.by_status() == {
        "importable": 1,
        "partial": 1,
        "manual": 0,
        "unsupported": 1,
        "skipped-secret": 1,
    }


def test_migration_object_map_validates_status_requirements() -> None:
    with pytest.raises(ValidationError, match="target_id"):
        MigrationObjectMap(
            source_id="agent",
            source_type="agent",
            target_schema="craik.agent_profile",
            target_id=None,
            status="importable",
            target_summary="Agent.",
        )

    with pytest.raises(ValidationError, match="secret_fields"):
        MigrationObjectMap(
            source_id="provider",
            source_type="model",
            target_schema="craik.model_provider",
            target_id=None,
            status="skipped-secret",
            target_summary="Provider.",
        )


def test_migration_field_map_validates_supported_and_unsupported_fields() -> None:
    with pytest.raises(ValidationError, match="target_field"):
        MigrationFieldMap(
            source_field="name",
            target_field=None,
            support="supported",
            transform_notes="Missing target.",
        )

    with pytest.raises(ValidationError, match="unsupported_reason"):
        MigrationFieldMap(
            source_field="secret_value",
            target_field=None,
            support="unsupported",
            transform_notes="Secrets are not imported.",
        )


def test_migration_map_requires_policy_evidence_and_receipts() -> None:
    with pytest.raises(ValidationError, match="policy_envelope_id"):
        MigrationMap(
            id="migration_map_memory",
            surface="memory",
            source_name="Adjacent Memory Store",
            field_maps=[
                MigrationFieldMap(
                    source_field="subject",
                    target_field="entity",
                    support="supported",
                    transform_notes="Use source subject as fact entity.",
                )
            ],
            policy_envelope_id="",
            evidence_ids=["evidence_map"],
            receipt_ids=["receipt_map"],
        )

    with pytest.raises(ValidationError):
        MigrationMap(
            id="migration_map_memory",
            surface="memory",
            source_name="Adjacent Memory Store",
            field_maps=[
                MigrationFieldMap(
                    source_field="subject",
                    target_field="entity",
                    support="supported",
                    transform_notes="Use source subject as fact entity.",
                )
            ],
            policy_envelope_id="policy_migration",
            evidence_ids=[],
            receipt_ids=["receipt_map"],
        )
