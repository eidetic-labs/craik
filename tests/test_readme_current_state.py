from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def readme_content() -> str:
    readme = Path(__file__).resolve().parents[1] / "README.md"
    return readme.read_text(encoding="utf-8")


def test_readme_getting_started_and_operator_modes_match_v0121(
    readme_content: str,
) -> None:
    assert "v0.12.1 supersedes v0.12.0" in readme_content
    assert "## Getting Started" in readme_content
    assert "## Operator Modes" in readme_content
    assert "craik auth login openai" in readme_content
    assert "craik model set openai/gpt-4o-mini" in readme_content
    assert 'echo "summarize the README" | craik chat -q -' in readme_content
    assert "Single-operator local (default)" in readme_content
    assert "CRAIK_OPERATOR_REQUIRED=1" in readme_content


def test_readme_stays_current_state_not_planning_doc(readme_content: str) -> None:
    forbidden = [
        "## Planning Docs",
        "## Documentation",
        "## Current Status",
        "## Initial Build Target",
        "## First Demo Target",
        "MVP",
        "mvp",
        "Roadmap",
        "roadmap",
        "Implementation Plan",
        "implementation-plan",
    ]
    for phrase in forbidden:
        assert phrase not in readme_content, f"Forbidden phrase found in README: {phrase!r}"
