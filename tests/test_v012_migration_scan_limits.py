from __future__ import annotations

import json
from pathlib import Path

import pytest

from craik.runtime.projects.migration import adjacent_runtime


def _write_record(path: Path, *, record_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"id": record_id, "type": "agent", "name": record_id}),
        encoding="utf-8",
    )


def test_migration_scan_enforces_json_file_cap(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(adjacent_runtime, "_MAX_MIGRATION_FILES", 2)
    _write_record(tmp_path / "one.json", record_id="one")
    _write_record(tmp_path / "two.json", record_id="two")
    _write_record(tmp_path / "three.json", record_id="three")

    with pytest.raises(adjacent_runtime.MigrationSourceTooLarge, match="more than 2 JSON files"):
        adjacent_runtime.inspect_adjacent_runtime_source(tmp_path)


def test_migration_scan_skips_files_beyond_depth_limit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(adjacent_runtime, "_MAX_MIGRATION_DEPTH", 2)
    _write_record(tmp_path / "ok.json", record_id="ok")
    _write_record(tmp_path / "level1" / "level2" / "too_deep.json", record_id="deep")

    inspection = adjacent_runtime.inspect_adjacent_runtime_source(tmp_path)

    assert [record.summary for record in inspection.records] == ["agent record ok."]
