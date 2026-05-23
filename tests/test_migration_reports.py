import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.projects.migration.adjacent_runtime import report_adjacent_runtime_migration
from craik.runtime.projects.migration.reports import (
    MigrationReportItem,
    build_migration_report,
    format_migration_report,
)
from craik.runtime.projects.migration_maps import migration_map_for_object, migration_plan_map

runner = CliRunner()


def test_migration_report_sections_are_deterministic_and_safe() -> None:
    plan = migration_plan_map(
        plan_id="migration_plan_fixture",
        source_name="fixture",
        objects=[
            migration_map_for_object(source_id="z_unknown", source_type="widget"),
            migration_map_for_object(source_id="a_agent", source_type="agent"),
            migration_map_for_object(source_id="m_model", source_type="model"),
            migration_map_for_object(source_id="c_channel", source_type="channel"),
            migration_map_for_object(
                source_id="s_secret",
                source_type="model",
                secret_fields=["api_key"],
            ),
            migration_map_for_object(source_id="g_gateway", source_type="gateway"),
        ],
    )

    report = build_migration_report(
        plan,
        created_at=datetime(2026, 5, 23, 5, 5, tzinfo=UTC),
    )
    payload = report.model_dump(mode="json")

    assert report.summary == {
        "importable": 1,
        "partial": 2,
        "manual": 1,
        "unsupported": 1,
        "skipped-secret": 1,
    }
    assert [item.source_id for item in report.importable_objects] == ["a_agent"]
    assert [item.source_id for item in report.manual_actions] == [
        "c_channel",
        "g_gateway",
        "m_model",
    ]
    manual_actions_by_id = {item.source_id: item for item in report.manual_actions}
    assert manual_actions_by_id["g_gateway"].status == "manual"
    assert manual_actions_by_id["c_channel"].status == "partial"
    assert manual_actions_by_id["m_model"].status == "partial"
    assert sorted({item.status for item in report.manual_actions}) == ["manual", "partial"]
    assert report.skipped_secrets[0].secret_fields == ["api_key"]
    assert report.unsupported_capabilities[0].source_id == "z_unknown"
    assert any(
        "credential material must be reconfigured" in item
        for item in report.security_posture_changes
    )
    assert "sk_live" not in json.dumps(payload)


def test_migration_report_text_includes_next_commands_and_validation() -> None:
    plan = migration_plan_map(
        plan_id="migration_plan_fixture",
        source_name="fixture",
        objects=[
            migration_map_for_object(source_id="agent", source_type="agent"),
            migration_map_for_object(source_id="channel", source_type="channel"),
        ],
    )

    report = build_migration_report(plan)
    lines = format_migration_report(report)

    assert "Recommended next commands:" in lines
    assert "Validation checklist:" in lines
    assert any("channel webhook signature" in line for line in lines)


def test_migration_report_rejects_raw_secret_like_text() -> None:
    with pytest.raises(ValidationError, match="raw secret"):
        MigrationReportItem(
            source_id="provider",
            target_schema="craik.model_provider",
            status="skipped-secret",
            summary="contains sk_live_secret_value",
            secret_fields=["api_key"],
        )


def test_adjacent_runtime_report_cli_is_redacted(tmp_path: Path) -> None:
    source = tmp_path / "adjacent"
    source.mkdir()
    (source / "providers.json").write_text(
        json.dumps(
            [
                {
                    "id": "openai",
                    "provider": "openai",
                    "model": "gpt-4.1",
                    "api_key": "sk_live_should_not_escape",
                }
            ]
        ),
        encoding="utf-8",
    )

    report = report_adjacent_runtime_migration(source)
    result = runner.invoke(app, ["migrate", "report", "--source", str(source), "--json"])

    assert report.skipped_secrets[0].secret_fields == ["api_key"]
    assert result.exception is None, result.output
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["skipped_secrets"][0]["secret_fields"] == ["api_key"]
    assert "sk_live_should_not_escape" not in result.stdout
