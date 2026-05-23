import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from craik.cli import app
from craik.runtime.auth.operator import OperatorSession, OperatorSessionStore
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


def test_migrate_import_defaults_to_dry_run_and_applies_with_yes(tmp_path: Path) -> None:
    source = _fixture_source(tmp_path)
    home = tmp_path / "home"
    before = sorted(path.read_text(encoding="utf-8") for path in source.rglob("*.json"))

    dry_run = runner.invoke(
        app,
        ["migrate", "import", "--source", str(source), "--json"],
        env={"CRAIK_HOME": str(home)},
    )
    apply = runner.invoke(
        app,
        ["migrate", "import", "--source", str(source), "--apply", "--yes", "--json"],
        env={"CRAIK_HOME": str(home)},
    )
    _put_operator_session(home)
    agents = runner.invoke(app, ["agent", "list"], env={"CRAIK_HOME": str(home)})

    after = sorted(path.read_text(encoding="utf-8") for path in source.rglob("*.json"))
    assert dry_run.exit_code == 0
    assert json.loads(dry_run.stdout)["mutated_state"] is False
    assert apply.exit_code == 0, apply.output
    apply_payload = json.loads(apply.stdout)
    assert apply_payload["mutated_state"] is True
    assert apply_payload["mutated_source"] is False
    assert any(
        record["target_schema"] == "craik.agent_profile"
        for record in apply_payload["applied_records"]
    )
    skipped_records = [
        record for record in apply_payload["applied_records"] if record["status"] == "skipped"
    ]
    assert skipped_records
    assert all(
        "record was not written to Craik state" in " ".join(record["warnings"])
        for record in skipped_records
    )
    assert any(
        record["status"] == "skipped"
        and record["target_schema"] in {"craik.model_provider", "craik.memory_record"}
        for record in apply_payload["applied_records"]
    )
    assert agents.exit_code == 0
    assert any(
        session["id"].startswith("migrated_") for session in json.loads(agents.stdout)
    )
    assert after == before


def test_migrate_import_apply_prompts_without_yes(tmp_path: Path) -> None:
    source = _fixture_source(tmp_path)

    result = runner.invoke(
        app,
        ["migrate", "import", "--source", str(source), "--apply"],
        input="n\n",
        env={"CRAIK_HOME": str(tmp_path / "home")},
    )

    assert result.exit_code != 0
    assert "Apply importable adjacent-runtime records" in result.output


def test_migrate_import_apply_include_records_filter(tmp_path: Path) -> None:
    source = _fixture_source(tmp_path)
    home = tmp_path / "home"
    plan = plan_adjacent_runtime_migration(source)
    selected = next(
        record.source_id
        for record in plan.mapped_records
        if record.target_schema == "craik.agent_profile"
    )

    result = runner.invoke(
        app,
        [
            "migrate",
            "import",
            "--source",
            str(source),
            "--apply",
            "--yes",
            "--include-records",
            selected,
            "--json",
        ],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert [record["source_id"] for record in payload["applied_records"]] == [selected]
    assert payload["applied_records"][0]["status"] == "applied"


def test_migrate_import_apply_include_non_agent_record_is_explicitly_skipped(
    tmp_path: Path,
) -> None:
    source = _fixture_source(tmp_path)
    home = tmp_path / "home"
    plan = plan_adjacent_runtime_migration(source)
    selected = next(
        record.source_id
        for record in plan.mapped_records
        if record.target_schema == "craik.model_provider"
    )

    result = runner.invoke(
        app,
        [
            "migrate",
            "import",
            "--source",
            str(source),
            "--apply",
            "--yes",
            "--include-records",
            selected,
            "--json",
        ],
        env={"CRAIK_HOME": str(home)},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert [record["source_id"] for record in payload["applied_records"]] == [selected]
    record = payload["applied_records"][0]
    assert record["status"] == "skipped"
    assert record["target_schema"] == "craik.model_provider"
    assert "record was not written to Craik state" in " ".join(record["warnings"])


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


def _put_operator_session(home: Path) -> None:
    OperatorSessionStore(home).put(
        OperatorSession(
            subject="operator:test",
            issuer="issuer",
            groups=["operators"],
            id_token_jti="jti",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
