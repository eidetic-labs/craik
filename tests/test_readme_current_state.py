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


def test_readme_coverage_badge_renders_before_release_pages_publish(
    readme_content: str,
) -> None:
    assert (
        "[![Coverage](https://img.shields.io/badge/coverage-87%25-green)]"
        "(docs/guides/coverage.md)"
    ) in readme_content
    assert "img.shields.io/endpoint" not in readme_content
    assert "coverage-badge.svg)]" not in readme_content


def test_readme_exposes_release_status_badges(readme_content: str) -> None:
    assert "actions/workflows/ci.yml/badge.svg" in readme_content
    assert "conformance-contract%20gate-blue" in readme_content
    assert "img.shields.io/pypi/v/craik?label=pypi" in readme_content
    assert "license-MIT-blue.svg" in readme_content
    assert "stability-pre--alpha-orange.svg" in readme_content


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
