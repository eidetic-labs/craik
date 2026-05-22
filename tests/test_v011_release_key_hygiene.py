import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_signing_key_export_is_gitignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "craik-release-signing-key.asc"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "craik-release-signing-key.asc"


def test_desktop_url_scheme_docs_are_review_only() -> None:
    docs = (
        ROOT / "docs" / "guides" / "companion-app-security.md"
    ).read_text(encoding="utf-8")

    assert "craik://" in docs
    assert "must never" in docs
    assert "auto-approve" in docs
