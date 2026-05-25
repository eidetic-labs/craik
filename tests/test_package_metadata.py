from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import craik

ROOT = Path(__file__).resolve().parents[1]
RELEASE_HEADING_RE = re.compile(
    r"^## (\d+\.\d+\.\d+) (?:-|—) \d{4}-\d{2}-\d{2}$",
    re.MULTILINE,
)


def test_package_python_range_supports_current_python_releases() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["requires-python"] == ">=3.12"


def test_package_version_matches_project_metadata() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert craik.__version__ == pyproject["project"]["version"]
    assert craik.__all__ == ["__version__"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", craik.__version__)


def test_docs_package_version_matches_project_metadata() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((ROOT / "docs" / "package.json").read_text(encoding="utf-8"))
    package_lock = json.loads((ROOT / "docs" / "package-lock.json").read_text(encoding="utf-8"))

    assert package["version"] == pyproject["project"]["version"]
    assert package_lock["version"] == pyproject["project"]["version"]
    assert package_lock["packages"][""]["version"] == pyproject["project"]["version"]


def test_uv_lock_editable_package_version_matches_project_metadata() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    uv_lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))

    craik_package = next(
        package
        for package in uv_lock["package"]
        if package["name"] == "craik" and package.get("source") == {"editable": "."}
    )
    assert craik_package["version"] == pyproject["project"]["version"]


def test_package_uses_pydantic_with_python_314_wheel_support() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "pydantic==2.13.4" in pyproject["project"]["dependencies"]


def test_changelog_has_section_for_current_package_version() -> None:
    """The first dated CHANGELOG section must match the package version.

    Catches release-prep mistakes where the version is bumped but the
    ``## Unreleased`` block is not renamed to ``## X.Y.Z — YYYY-MM-DD``.
    """
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    expected = pyproject["project"]["version"]

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    versions = RELEASE_HEADING_RE.findall(changelog)

    assert versions, "CHANGELOG.md has no dated release sections"
    assert versions[0] == expected, (
        f"CHANGELOG.md top dated section is {versions[0]} but pyproject.toml declares {expected}"
    )


def test_release_readiness_current_gate_matches_project_metadata() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    expected = pyproject["project"]["version"]

    readiness = (ROOT / "docs" / "release-readiness.md").read_text(encoding="utf-8")

    assert f"pre-release gate is `{expected}`" in readiness
    assert f"## v{expected} " in readiness
    assert f"### v{expected} Validation Commands" in readiness
    assert "uv run python scripts/check_oauth_callback_safety.py" in readiness
    assert "uv run python scripts/check_text_selection_wiring.py" in readiness
