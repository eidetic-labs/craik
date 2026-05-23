from __future__ import annotations

from pathlib import Path


def test_readme_getting_started_and_operator_modes_match_v0121() -> None:
    readme = Path(__file__).resolve().parents[1] / "README.md"
    content = readme.read_text(encoding="utf-8")

    assert "v0.12.1 supersedes v0.12.0" in content
    assert "## Getting Started" in content
    assert "## Operator Modes" in content
    assert "craik auth login openai" in content
    assert "craik model set openai/gpt-4o-mini" in content
    assert 'echo "summarize the README" | craik chat -q -' in content
    assert "Single-operator local (default)" in content
    assert "CRAIK_OPERATOR_REQUIRED=1" in content
