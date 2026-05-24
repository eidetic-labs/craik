# Coverage Reports

<p className="craik-meta"><span>2 min read</span><span>For contributors</span><span>Updated 2026-05-24</span></p>

<div className="craik-lead">

**What ships with a release**

Release tags generate HTML coverage, a `coverage.xml` artifact, and a README
badge so contributors can inspect the tested surface without running the full
suite locally.

</div>

## Published Report

The release coverage workflow runs on tag pushes and manual dispatch. It runs
the pytest suite with `pytest-cov`, writes terminal, HTML, and XML coverage
reports, publishes `htmlcov/` to GitHub Pages, and attaches `coverage.xml` to
the matching GitHub Release.

The README badge links to the published HTML report:

```text
https://eidetic-labs.github.io/craik/
```

## Local Equivalent

Run the same coverage command locally before release prep:

```bash
uv run pytest --cov=craik --cov-report=term --cov-report=html --cov-report=xml
```

The threshold is configured in `pyproject.toml`. Raise it only after `main`
has stayed green at the higher threshold.

## Reading the Report

Use the report to answer focused review questions:

- Which new code paths have no direct tests?
- Which changed files rely only on broad integration coverage?
- Which branches need a negative or failure-path test before release?

Coverage is a guardrail, not proof of correctness. Security, migration,
provider, and TUI behavior still need targeted tests that exercise the user
workflow and failure mode.

