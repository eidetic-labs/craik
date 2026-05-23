import json
from pathlib import Path

from craik.runtime.projects.migration.adjacent_runtime import (
    inspect_adjacent_runtime_source,
    plan_adjacent_runtime_migration,
    report_adjacent_runtime_migration,
)

FIXTURES = Path(__file__).parent / "fixtures" / "adjacent_runtime"


def test_full_adjacent_runtime_fixture_drives_import_plan() -> None:
    source = FIXTURES / "full"

    inspection = inspect_adjacent_runtime_source(source)
    report = plan_adjacent_runtime_migration(source)
    payload = report.model_dump(mode="json")

    assert len(inspection.records) == 14
    assert inspection.secret_record_count == 2
    assert len(report.candidates) == 14
    assert {record.target_schema for record in report.mapped_records} >= {
        "craik.agent_profile",
        "craik.model_provider",
        "craik.model_fallback_chain",
        "craik.profile",
        "craik.channel_binding",
        "craik.memory_record",
        "craik.skill_package",
        "craik.agent_session",
        "craik.schedule",
        "craik.sandbox_config",
        "craik.gateway_config",
        "craik.approval_security_posture",
    }
    assert "fixture-openai-key" not in json.dumps(payload)
    assert "fixture-webhook-secret" not in json.dumps(payload)


def test_full_adjacent_runtime_fixture_drives_report_sections() -> None:
    report = report_adjacent_runtime_migration(FIXTURES / "full")

    assert report.summary == {
        "importable": 4,
        "manual": 5,
        "partial": 3,
        "skipped-secret": 2,
        "unsupported": 0,
    }
    assert report.skipped_secrets
    assert report.manual_actions
    assert any("gateway" in item.lower() for item in report.security_posture_changes)


def test_invalid_adjacent_runtime_fixture_is_reported_without_failure() -> None:
    inspection = inspect_adjacent_runtime_source(FIXTURES / "invalid")

    assert inspection.records == ()
    assert inspection.warnings
    assert "skipped invalid JSON" in inspection.warnings[0]
