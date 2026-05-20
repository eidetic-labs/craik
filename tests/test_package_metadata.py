from __future__ import annotations

import tomllib
from pathlib import Path

import craik

ROOT = Path(__file__).resolve().parents[1]


def test_package_python_range_supports_current_python_releases() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["requires-python"] == ">=3.12"


def test_package_version_matches_project_metadata() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert craik.__version__ == pyproject["project"]["version"]


def test_package_uses_pydantic_with_python_314_wheel_support() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "pydantic==2.13.4" in pyproject["project"]["dependencies"]
