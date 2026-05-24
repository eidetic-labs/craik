# Coverage Reports

<p className="craik-meta"><span>2 min read</span><span>For contributors</span><span>Updated 2026-05-24</span></p>

<div className="craik-lead">

**What ships with a release**

Release tags generate HTML coverage, a `coverage.xml` artifact, a Shields-backed
README badge endpoint, and a generated SVG badge so contributors can inspect the
tested surface without running the full suite locally.

</div>

## Published Report

The release coverage workflow runs on tag pushes and manual dispatch. It runs
the pytest suite with `pytest-cov`, writes terminal, HTML, XML, and badge
endpoint reports, publishes `htmlcov/` to GitHub Pages, and attaches
`coverage.xml` to the matching GitHub Release.

The README badge is rendered through Shields from the published badge endpoint
and links to the published HTML report:

```text
https://eidetic-labs.github.io/craik/
```

## Local Equivalent

Run the same coverage command locally before release prep:

```bash
uv run pytest --cov=craik --cov-report=term --cov-report=html --cov-report=xml
```

The default local threshold is configured in `pyproject.toml`.

## Coverage Threshold

The release workflow enforces a minimum overall coverage of **80%**. If a
release-tag push drops total coverage below this threshold, the coverage
workflow fails before publishing the Pages report or attaching `coverage.xml`
to the GitHub Release.

The threshold is set below the current measured full-suite coverage to allow
normal variance from feature work. Raise it only after `main` has stayed green
at the higher threshold. Lower it only with explicit maintainer rationale and a
follow-up issue to recover the floor.

## Reading the Report

Use the report to answer focused review questions:

- Which new code paths have no direct tests?
- Which changed files rely only on broad integration coverage?
- Which branches need a negative or failure-path test before release?

Coverage is a guardrail, not proof of correctness. Security, migration,
provider, and TUI behavior still need targeted tests that exercise the user
workflow and failure mode.
