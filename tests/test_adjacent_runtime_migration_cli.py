import json
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.projects.migration.adjacent_runtime import (
    inspect_adjacent_runtime_source,
    plan_adjacent_runtime_migration,
)

runner = CliRunner()


def test_adjacent_runtime_inspect_discovers_records_and_redacts_secret_fields(
    tmp_path: Path,
) -> None:
    source = _fixture_source(tmp_path)

    inspection = inspect_adjacent_runtime_source(source)

    assert len(inspection.records) == 4
    secret_record = next(record for record in inspection.records if record.contains_secret)
    assert secret_record.secret_fields == ("api_key",)
    assert "sk_live" not in secret_record.summary


def test_adjacent_runtime_plan_maps_records_without_copying_secret_values(
    tmp_path: Path,
) -> None:
    source = _fixture_source(tmp_path)

    report = plan_adjacent_runtime_migration(source)
    payload = report.model_dump(mode="json")

    assert report.mutated_state is False
    assert {record.target_schema for record in report.mapped_records} >= {
        "craik.agent_profile",
        "craik.model_provider",
        "craik.memory_record",
    }
    assert any(record.status == "warning" for record in report.mapped_records)
    assert "sk_live" not in json.dumps(payload)


def test_migrate_inspect_json_cli(tmp_path: Path) -> None:
    source = _fixture_source(tmp_path)

    result = runner.invoke(app, ["migrate", "inspect", "--source", str(source), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["kind"] == "agent-runtime"
    assert payload["record_count"] == 4
    assert payload["secret_record_count"] == 1
    assert "sk_live" not in result.stdout


def test_migrate_plan_text_cli(tmp_path: Path) -> None:
    source = _fixture_source(tmp_path)

    result = runner.invoke(app, ["migrate", "plan", "--source", str(source)])

    assert result.exit_code == 0
    assert "Migration dry run:" in result.stdout
    assert "Mutated source: no" in result.stdout
    assert "craik.agent_profile" in result.stdout
    assert "sk_live" not in result.stdout


def test_migrate_import_defaults_to_dry_run_and_rejects_apply(tmp_path: Path) -> None:
    source = _fixture_source(tmp_path)
    before = sorted(path.read_text(encoding="utf-8") for path in source.rglob("*.json"))

    dry_run = runner.invoke(app, ["migrate", "import", "--source", str(source), "--json"])
    apply = runner.invoke(app, ["migrate", "import", "--source", str(source), "--apply"])

    after = sorted(path.read_text(encoding="utf-8") for path in source.rglob("*.json"))
    assert dry_run.exit_code == 0
    assert json.loads(dry_run.stdout)["mutated_state"] is False
    assert apply.exit_code != 0
    assert "apply mode is not enabled" in apply.stdout
    assert after == before


def test_migrate_rejects_unsupported_kind(tmp_path: Path) -> None:
    source = _fixture_source(tmp_path)

    result = runner.invoke(
        app,
        ["migrate", "inspect", "--source", str(source), "--kind", "unknown"],
    )

    assert result.exit_code != 0
    assert "unsupported migration kind" in result.stdout


def _fixture_source(tmp_path: Path) -> Path:
    source = tmp_path / "adjacent"
    source.mkdir()
    (source / "agents.json").write_text(
        json.dumps(
            {
                "agents": [
                    {"id": "reviewer", "type": "agent", "model": "gpt-4.1"},
                    {
                        "id": "builder",
                        "type": "agent",
                        "provider": "openai",
                        "api_key": "sk_live_should_not_escape",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (source / "memory.json").write_text(
        json.dumps([{"id": "memory_1", "type": "memory", "subject": "docs"}]),
        encoding="utf-8",
    )
    (source / "providers.json").write_text(
        json.dumps([{"id": "openai_primary", "provider": "openai", "model": "gpt-4.1"}]),
        encoding="utf-8",
    )
    return source
