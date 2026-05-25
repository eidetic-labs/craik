from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_product_site_workflow_owns_github_pages_deploy() -> None:
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(
        encoding="utf-8"
    )

    assert "actions/deploy-pages@" in workflow
    assert "path: site" in workflow
    expected_host = ".".join(("craik", "eidetic-labs", "com"))
    cname = ROOT / "site" / "CNAME"
    assert cname.read_text(encoding="utf-8").splitlines() == [expected_host]


def test_coverage_workflow_does_not_deploy_github_pages() -> None:
    workflow = (ROOT / ".github" / "workflows" / "coverage.yml").read_text(
        encoding="utf-8"
    )

    forbidden = [
        "pages: write",
        "id-token: write",
        "actions/upload-pages-artifact@",
        "actions/deploy-pages@",
    ]
    for phrase in forbidden:
        assert phrase not in workflow, (
            f"coverage workflow must not publish GitHub Pages: {phrase!r}"
        )
    assert "actions/upload-artifact@" in workflow
    assert "htmlcov/" in workflow
