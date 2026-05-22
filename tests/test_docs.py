import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED_DOC_PARTS = {".docusaurus", "build", "node_modules"}
IGNORED_DOC_PREFIXES = {(Path("docs") / "blog"), (Path("docs") / "docs")}
DOC_PATHS = [
    Path("README.md"),
    *sorted(
        path
        for path in Path("docs").rglob("*.md")
        if not IGNORED_DOC_PARTS.intersection(path.parts)
        and not any(path.is_relative_to(prefix) for prefix in IGNORED_DOC_PREFIXES)
    ),
]
LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def test_local_markdown_links_resolve() -> None:
    missing: list[str] = []
    for relative in DOC_PATHS:
        source = ROOT / relative
        for raw_target in LINK_PATTERN.findall(source.read_text()):
            target = raw_target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            candidate = (source.parent / target).resolve()
            if not candidate.exists():
                missing.append(f"{relative}: {raw_target}")

    assert missing == []


def test_v0_docs_tree_covers_required_areas() -> None:
    required = [
        "docs/index.md",
        "docs/concepts/case-files.md",
        "docs/concepts/governance.md",
        "docs/concepts/handoffs.md",
        "docs/concepts/memory-and-stigmem.md",
        "docs/concepts/receipts.md",
        "docs/concepts/work-graph.md",
        "docs/guides/installation.md",
        "docs/guides/quickstart.md",
        "docs/reference/cli.md",
        "docs/reference/config.md",
        "docs/reference/memory-backends.md",
        "docs/reference/policy-profiles.md",
        "docs/reference/schemas.md",
        "docs/security/secrets.md",
        "docs/limitations.md",
    ]

    assert [path for path in required if not (ROOT / path).exists()] == []


def test_stigmem_demo_tutorial_matches_quickstart_smoke() -> None:
    tutorial = (ROOT / "docs" / "guides" / "stigmem-docs-demo.md").read_text()
    quickstart = (ROOT / "docs" / "guides" / "quickstart.md").read_text()
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    smoke_command = "craik demo stigmem-docs --repo-path . --no-github"

    assert smoke_command in tutorial
    assert smoke_command in quickstart
    assert "python scripts/quickstart_smoke.py" in ci
    assert "provider_openai" in tutorial
    assert "provider_anthropic" in tutorial


def test_post_mvp_deferral_docs_keep_scope_honest() -> None:
    post_mvp = (ROOT / "docs" / "reference" / "post-mvp-scope.md").read_text()
    limitations = (ROOT / "docs" / "limitations.md").read_text()
    gateway = (ROOT / "docs" / "reference" / "gateway-daemon.md").read_text()
    operator = (ROOT / "docs" / "reference" / "operator-surface.md").read_text()
    runners = (ROOT / "docs" / "reference" / "runner-adapter-contract.md").read_text()
    skills = (ROOT / "docs" / "guides" / "community-skills.md").read_text()
    plugins = (ROOT / "docs" / "guides" / "community-plugins.md").read_text()

    for required in [
        "Gateway Daemon",
        "Operator UI",
        "Additional Live Runners",
        "Companion And Visual Surfaces",
        "Marketplace And Community Ecosystem",
    ]:
        assert required in post_mvp

    assert "Gateway daemon mode is foreground and local-first" in gateway
    assert "Production dispatch loop" in gateway
    assert "A complete TUI" in operator
    assert "dashboard is post-MVP scope" in operator
    assert "Additional live runner adapters are post-MVP" in runners
    assert "marketplace workflows are post-MVP scope" in skills
    assert "marketplace and community ecosystem workflows are post-MVP scope" in plugins
    assert "Post-MVP Scope](reference/post-mvp-scope.md)" in limitations
